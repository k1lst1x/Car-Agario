# game/views.py
from django.shortcuts import render
from .models import GameSession


def arena(request, session_id=None):
    # если пришли по корню "/", создаём / берём комнату с id=1
    if session_id is None:
        session_id = 1

    session, _ = GameSession.objects.get_or_create(pk=int(session_id))
    return render(request, "game/arena.html", {"session_id": session.id})
