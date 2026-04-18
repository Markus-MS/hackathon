from __future__ import annotations

import sqlite3

from flagfarm.services import ctf_service


DEMO_CHALLENGES = [
    {
        "remote_id": "warmup-recon",
        "name": "Warmup Recon",
        "category": "web",
        "points": 100,
        "difficulty": "easy",
        "description": "Find the flag hidden in a lightly obfuscated robots.txt trail.",
        "solves": 312,
        "connection_info": "https://demo.flagfarm.local/warmup",
    },
    {
        "remote_id": "baby-rop",
        "name": "Baby ROP",
        "category": "pwn",
        "points": 200,
        "difficulty": "medium",
        "description": "Use a short return-oriented payload to pivot into win().",
        "solves": 184,
        "connection_info": "nc baby-rop.demo 31337",
    },
    {
        "remote_id": "broken-session",
        "name": "Broken Session",
        "category": "web",
        "points": 300,
        "difficulty": "medium",
        "description": "Exploit cookie confusion in a Flask session serializer.",
        "solves": 120,
        "connection_info": "https://demo.flagfarm.local/session",
    },
    {
        "remote_id": "elliptic-picnic",
        "name": "Elliptic Picnic",
        "category": "crypto",
        "points": 400,
        "difficulty": "hard",
        "description": "Recover the key from a biased nonce flow.",
        "solves": 74,
        "connection_info": "Download: elliptic-picnic.zip",
    },
    {
        "remote_id": "firmware-graveyard",
        "name": "Firmware Graveyard",
        "category": "rev",
        "points": 350,
        "difficulty": "hard",
        "description": "Extract a hard-coded flag path from a stripped MIPS image.",
        "solves": 81,
        "connection_info": "Download: graveyard.bin",
    },
    {
        "remote_id": "kernel-ghost",
        "name": "Kernel Ghost",
        "category": "pwn",
        "points": 500,
        "difficulty": "insane",
        "description": "Privilege escalate through a custom device ioctl race.",
        "solves": 19,
        "connection_info": "nc kernel-ghost.demo 31338",
    },
]


def seed_demo_week(db: sqlite3.Connection) -> int:
    existing = db.execute(
        "SELECT id FROM ctf_events WHERE slug = 'demo-week-1'"
    ).fetchone()
    if existing is not None:
        ctf_id = int(existing["id"])
    else:
        ctf_id = ctf_service.create_ctf(
            db,
            {
                "title": "Demo Week 1",
                "ctfd_url": "https://demo.ctfd.local",
                "ctfd_token": "demo-token",
            },
        )
        db.execute(
            "UPDATE ctf_events SET slug = 'demo-week-1' WHERE id = ?",
            (ctf_id,),
        )
        db.commit()

    ctf_service.upsert_challenges(db, ctf_id=ctf_id, challenges=DEMO_CHALLENGES)
    ctf_service.activate_ctf(db, ctf_id)

    for model in ctf_service.list_models(db, enabled_only=True):
        ctf_service.upsert_ctf_account(
            db,
            ctf_id=ctf_id,
            model_id=model["id"],
            username=f"{model['slug']}-bot",
            password="demo-password",
            team_name=f"{model['display_name']} Team",
            notes="Seeded by demo bootstrap.",
        )

    return ctf_id
