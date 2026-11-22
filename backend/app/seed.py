import random
import subprocess
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app import storage
from app.models import (
    Channel,
    Comment,
    Playlist,
    PlaylistItem,
    Report,
    Role,
    Subscription,
    User,
    Video,
    VideoLike,
    VideoShare,
    VideoStatus,
    Visibility,
)
from app.security import hash_password
from app.transcode import SyncSession, process_video

PASSWORD = "demo12345"
USERS = [
    ("admin", Role.admin, "Администратор платформы"),
    ("moderator", Role.moderator, "Слежу за порядком"),
    (
        "alice",
        Role.user,
        "Тестовые паттерны и цветовые шкалы. Новые видео каждую неделю.",
    ),
    ("bob", Role.user, "Канал Боба: эксперименты со звуком и картинкой."),
    ("carol", Role.user, "Carol - короткие демо-ролики."),
]

VIDEOS = [
    (
        "alice",
        "Тестовая таблица: как настроить монитор",
        "Классическая тестовая таблица для проверки цвета и четкости.",
        "public",
        "testsrc2",
        440,
    ),
    (
        "alice",
        "SMPTE цветные полосы — 4K ready",
        "Эталонные цветные полосы. Подходит для калибровки.",
        "public",
        "smptebars",
        523,
    ),
    (
        "alice",
        "Градиенты для медитации",
        "Плавные градиенты и спокойный звук.",
        "public",
        "gradients",
        330,
    ),
    (
        "bob",
        "RGB тест-паттерн за 6 секунд",
        "Короткий ролик с RGB-паттерном.",
        "public",
        "rgbtestsrc",
        660,
    ),
    (
        "bob",
        "Эксперимент: тон 880 Гц",
        "Чистый синус и тестовая картинка.",
        "public",
        "testsrc2",
        880,
    ),
    (
        "bob",
        "Приватный ролик для друзей",
        "Доступен только Алисе (выдан доступ владельцем).",
        "private",
        "smptebars",
        392,
    ),
    (
        "carol",
        "Ролик по ссылке (unlisted)",
        "Не отображается в ленте и поиске, открывается по прямой ссылке.",
        "unlisted",
        "gradients",
        494,
    ),
    (
        "carol",
        "Нарушающее правила видео (скрыто модератором)",
        "Пример скрытого видео для проверки модерации.",
        "public",
        "testsrc2",
        262,
    ),
    (
        "carol",
        "Полезный туториал: как грузить видео",
        "Демонстрация загрузки и обработки.",
        "public",
        "rgbtestsrc",
        587,
    ),
]
COMMENTS = [
    "Отличный ролик, спасибо!",
    "Первый! 🙂",
    "А можно подольше?",
    "Очень пригодилось для настройки",
    "Не работает на моем телевизоре, но на ноутбуке всем супер",
    "Подписался, жду новых видео",
    "Звук чуть тише бы сделать",
    "Лучшая тестовая таблица на платформе",
]


def _make_source(path, source, freq):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"{source}=size=1280x720:rate=25",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq}:sample_rate=44100",
            "-t",
            "6",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        timeout=300,
    )


def main():
    rnd = random.Random(42)
    storage.ensure_bucket()

    with SyncSession() as s:
        users: dict[str, User] = {}
        channels: dict[str, Channel] = {}

        for name, role, about in USERS:
            u = s.execute(
                select(User).where(User.username == name)
            ).scalar_one_or_none()

            if not u:
                u = User(
                    email=f"{name}@demo.local",
                    username=name,
                    password_hash=hash_password(PASSWORD),
                    role=role,
                )

                s.add(u)
                s.flush()

                s.add(
                    Channel(
                        owner_id=u.id,
                        handle=name,
                        name=name.capitalize(),
                        description=about,
                    )
                )
                s.flush()

            users[name] = u
            channels[name] = s.execute(
                select(Channel).where(Channel.owner_id == u.id)
            ).scalar_one()

        s.commit()

        videos: dict[str, uuid.UUID] = {}
        new_ids: list[uuid.UUID] = []

        for owner, title, desc, vis, src, freq in VIDEOS:
            ch = channels[owner]
            v = s.execute(
                select(Video).where(Video.channel_id == ch.id, Video.title == title)
            ).scalar_one_or_none()

            if v:
                videos[title] = v.id
                continue

            vid = uuid.uuid4()
            key = f"videos/{vid}/source"

            with tempfile.TemporaryDirectory() as tmp:
                f = Path(tmp) / "src.mp4"
                _make_source(f, src, freq)
                storage.upload_file(f, key, "video/mp4")
                size = f.stat().st_size

            s.add(
                Video(
                    id=vid,
                    channel_id=ch.id,
                    title=title,
                    description=desc,
                    visibility=Visibility(vis),
                    status=VideoStatus.processing,
                    source_key=key,
                    size_bytes=size,
                )
            )
            s.commit()

            process_video(vid)
            videos[title] = vid
            new_ids.append(vid)

            print(f"seed: video '{title}' ready")

        if not new_ids:
            print("seed: already seeded")

            return

        for vid in new_ids:
            s.execute(
                update(Video)
                .where(Video.id == vid)
                .values(views_count=rnd.randint(40, 5000))
            )

        titles = list(videos)
        public_ids = [videos[t] for t in titles if "Приватный" not in t]
        regular = [u for n, u in users.items() if n not in ("admin", "moderator")]

        for vid in public_ids:
            for u in regular:
                if rnd.random() < 0.8:
                    s.execute(
                        insert(VideoLike)
                        .values(
                            video_id=vid,
                            user_id=u.id,
                            value=1 if rnd.random() < 0.85 else -1,
                        )
                        .on_conflict_do_nothing()
                    )
        for vid in public_ids:
            top = []

            for u in rnd.sample(regular, k=min(3, len(regular))):
                c = Comment(video_id=vid, user_id=u.id, text=rnd.choice(COMMENTS))
                s.add(c)
                s.flush()
                top.append(c)

            s.add(
                Comment(
                    video_id=vid,
                    user_id=users["alice"].id,
                    parent_id=top[0].id,
                    text="Спасибо за отзыв!",
                )
            )

        for sub, ch in (
            ("bob", "alice"),
            ("carol", "alice"),
            ("alice", "bob"),
            ("alice", "carol"),
            ("bob", "carol"),
        ):
            s.execute(
                insert(Subscription)
                .values(subscriber_id=users[sub].id, channel_id=channels[ch].id)
                .on_conflict_do_nothing()
            )

        s.execute(
            insert(VideoShare)
            .values(
                video_id=videos["Приватный ролик для друзей"], user_id=users["alice"].id
            )
            .on_conflict_do_nothing()
        )

        pl = Playlist(
            channel_id=channels["alice"].id,
            title="Тест-паттерны",
            visibility=Visibility.public,
        )

        s.add(pl)
        s.flush()

        for i, t in enumerate(titles[:3], 1):
            s.add(PlaylistItem(playlist_id=pl.id, video_id=videos[t], position=i))

        hidden = videos["Нарушающее правила видео (скрыто модератором)"]
        s.execute(
            update(Video)
            .where(Video.id == hidden)
            .values(is_hidden=True, hidden_reason="Нарушение правил (демо)")
        )
        s.add(
            Report(
                video_id=videos["Эксперимент: тон 880 Гц"],
                reporter_id=users["carol"].id,
                reason="Слишком громкий звук",
            )
        )
        s.add(
            Report(
                video_id=videos["RGB тест-паттерн за 6 секунд"],
                reporter_id=users["alice"].id,
                reason="Спам",
            )
        )
        s.commit()

    print(
        f"seed: done. Логин: admin@demo.local / moderator@demo.local / alice@demo.local / bob@demo.local / "
        f"carol@demo.local, пароль {PASSWORD}"
    )


if __name__ == "__main__":
    main()
