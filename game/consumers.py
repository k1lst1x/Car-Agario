import asyncio
import json
import math
import random
import time

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

from .models import GameSession, Car

TICK = 0.05  # 20 циклов в сек.
MAP_SIZE = 2000
CAR_R = 12
BULLET_R = 3
ORB_R = 8
BULLET_SPEED = 600  # px/с


class GameConsumer(AsyncJsonWebsocketConsumer):
    # ---------- подключение -------------------------------------------------
    async def connect(self):
        self.session_id = int(self.scope["url_route"]["kwargs"]["session_id"])
        self.group_name = f"game_{self.session_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # ORM – только через async-обёртки
        self.session, _ = await self.get_or_create_session(self.session_id)
        self.car = await self.create_car(self.session)

        # ---------- общая структура комнаты (RAM) ----------------------------
        if not hasattr(self.channel_layer, "rooms"):
            self.channel_layer.rooms = {}
        self.room = self.channel_layer.rooms.setdefault(
            self.group_name,
            {"cars": {}, "bullets": [], "orbs": [], "loop_task": None},
        )
        self.room["cars"][self.car.id] = self._car_state()

        # первый игрок запускает цикл
        if self.room["loop_task"] is None:
            self.room["loop_task"] = asyncio.create_task(self.game_loop())

        await self.send_json(
            {
                "type": "init",
                "car_id": self.car.id,
                "stats": {
                    "hp": self.car.hp,
                    "speed": self.car.speed,
                    "damage": self.car.damage,
                    "fire_rate": self.car.fire_rate,
                },
            }
        )

    async def disconnect(self, code):
        self.room["cars"].pop(self.car.id, None)
        await self.delete_car(self.car)
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

        if not self.room["cars"] and self.room["loop_task"]:
            self.room["loop_task"].cancel()
            del self.channel_layer.rooms[self.group_name]

    # ---------- приём команд -------------------------------------------------
    async def receive_json(self, data, **kwargs):
        action = data.get("action")
        if action == "move":
            self._set_car_target(self.car.id, data["target"])
        elif action == "shoot":
            self._spawn_bullet(self.car.id)
        elif action == "upgrade":
            stat = data.get("stat")
            await self._attempt_upgrade(self.car.id, stat)

    # ---------- игровой цикл -------------------------------------------------
    async def game_loop(self):
        last = time.perf_counter()
        try:
            while True:
                await asyncio.sleep(TICK)
                now = time.perf_counter()
                dt = now - last
                last = now

                self._update_cars(dt)
                self._update_bullets(dt)
                self._apply_buffs(dt)
                self._handle_collisions()
                self._spawn_orbs()

                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        "type": "state_broadcast",
                        "snapshot": {
                            "type": "state",
                            "cars": self.room["cars"],
                            "bullets": self.room["bullets"],
                            "orbs": self.room["orbs"],
                        },
                    },
                )
        except asyncio.CancelledError:
            pass

    async def state_broadcast(self, event):
        await self.send_json(event["snapshot"])

    # ---------- helpers ------------------------------------------------------
    def _car_state(self):
        return {
            "x": MAP_SIZE / 2 + random.randint(-200, 200),
            "y": MAP_SIZE / 2 + random.randint(-200, 200),
            "vx": 0,
            "vy": 0,
            "dx": 0,  # нормализованный курс
            "dy": -1,
            "hp": self.car.hp,
            "speed": self.car.speed * 1000 / 3600,
            "damage": self.car.damage,
            "fire_rate": self.car.fire_rate,
            "gold": 1000,  # Стартовое золото для тестов
            "xp": 0,
            "buffs": {},
            "upgrades": {"hp": 0, "speed": 0, "damage": 0, "fire_rate": 0},
        }

    def _upgrade_cost(self, base_cost, level):
        return int(base_cost * (1.35**level))

    def _set_car_target(self, cid, target):
        car = self.room["cars"][cid]
        dx, dy = target["x"] - car["x"], target["y"] - car["y"]
        dist = math.hypot(dx, dy)
        if dist:
            v = car["speed"]
            car["vx"] = dx / dist * v
            car["vy"] = dy / dist * v
            car["dx"] = dx / dist
            car["dy"] = dy / dist

    def _update_cars(self, dt):
        for car in self.room["cars"].values():
            car["x"] += car["vx"] * dt
            car["y"] += car["vy"] * dt
            if car["x"] < CAR_R or car["x"] > MAP_SIZE - CAR_R:
                car["vx"] *= -1
            if car["y"] < CAR_R or car["y"] > MAP_SIZE - CAR_R:
                car["vy"] *= -1

    def _spawn_bullet(self, owner_id):
        car = self.room["cars"][owner_id]
        self.room["bullets"].append(
            {
                "x": car["x"] + car["dx"] * (CAR_R + 4),
                "y": car["y"] + car["dy"] * (CAR_R + 4),
                "vx": car["dx"] * BULLET_SPEED,
                "vy": car["dy"] * BULLET_SPEED,
                "owner": owner_id,
                "ttl": 2.0,
                "dmg": car["damage"],
            }
        )

    async def _attempt_upgrade(self, cid, stat):
        car = self.room["cars"][cid]
        base_cost = {"hp": 200, "speed": 300, "damage": 250, "fire_rate": 400}
        if stat in base_cost:
            level = car["upgrades"][stat]
            cost = self._upgrade_cost(base_cost[stat], level)
            if car["gold"] >= cost:
                car["gold"] -= cost
                car["upgrades"][stat] += 1
                if stat == "hp":
                    car["hp"] += 100
                elif stat == "speed":
                    car["speed"] += 10 * 1000 / 3600  # +10 км/ч
                elif stat == "damage":
                    car["damage"] += 10
                elif stat == "fire_rate":
                    car["fire_rate"] += 0.2  # +0.2 выстрелов в сек.
                await self.send_json(
                    {
                        "type": "upgrade_success",
                        "stat": stat,
                        "level": car["upgrades"][stat],
                        "gold": car["gold"],
                    }
                )
            else:
                await self.send_json(
                    {"type": "upgrade_fail", "reason": "Недостаточно золота"}
                )

    def _update_bullets(self, dt):
        alive = []
        for b in self.room["bullets"]:
            b["ttl"] -= dt
            if b["ttl"] > 0:
                b["x"] += b["vx"] * dt
                b["y"] += b["vy"] * dt
                alive.append(b)
        self.room["bullets"] = alive

    def _apply_buffs(self, dt):
        for car in self.room["cars"].values():
            expired = []
            for name, tl in car["buffs"].items():
                tl -= dt
                car["buffs"][name] = tl
                if tl <= 0:
                    expired.append(name)
            for name in expired:
                del car["buffs"][name]

    def _spawn_orbs(self):
        if random.random() < TICK * 0.2:
            self.room["orbs"].append(
                {
                    "x": random.randint(0, MAP_SIZE),
                    "y": random.randint(0, MAP_SIZE),
                    "kind": random.choice(
                        ["gold", "damage", "velocity", "vanish", "regen", "xp"]
                    ),
                    "ttl": 30.0,
                },
            )

    def _handle_collisions(self):
        # пули → машины
        survivors = []
        for b in self.room["bullets"]:
            hit = False
            for cid, car in self.room["cars"].items():
                if cid == b["owner"]:
                    continue
                if (
                    self._dist2(b["x"], b["y"], car["x"], car["y"])
                    <= (CAR_R + BULLET_R) ** 2
                ):
                    car["hp"] -= b["dmg"]
                    hit = True
            if not hit:
                survivors.append(b)
        self.room["bullets"] = survivors

        # машины ↔ орбы
        taken = set()
        for cid, car in self.room["cars"].items():
            for idx, o in enumerate(self.room["orbs"]):
                if idx in taken:
                    continue
                if (
                    self._dist2(car["x"], car["y"], o["x"], o["y"])
                    <= (CAR_R + ORB_R) ** 2
                ):
                    self._apply_orb(car, o["kind"])
                    taken.add(idx)
        self.room["orbs"] = [
            o for i, o in enumerate(self.room["orbs"]) if i not in taken
        ]

        # респавн
        dead = [cid for cid, car in self.room["cars"].items() if car["hp"] <= 0]
        for cid in dead:
            self.room["cars"][cid] = self._car_state()

    @staticmethod
    def _dist2(x1, y1, x2, y2):
        return (x1 - x2) ** 2 + (y1 - y2) ** 2

    def _apply_orb(self, car, kind):
        if kind == "gold":
            car["gold"] += 200
        elif kind == "xp":
            car["xp"] += 1
        elif kind == "damage":
            car["buffs"]["dmg"] = 6
        elif kind == "velocity":
            car["buffs"]["speed"] = 6
        elif kind == "vanish":
            car["buffs"]["vanish"] = 4
        elif kind == "regen":
            car["buffs"]["regen"] = 6

    # ORM async wrappers ------------------------------------------------------
    @database_sync_to_async
    def get_or_create_session(self, sid):
        return GameSession.objects.get_or_create(pk=sid)

    @database_sync_to_async
    def create_car(self, session):
        return Car.objects.create(
            session=session, nickname=f"Guest#{random.randint(1000, 9999)}"
        )

    @database_sync_to_async
    def delete_car(self, car):
        car.delete()
