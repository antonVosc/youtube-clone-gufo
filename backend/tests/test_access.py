import uuid

from app.routers.media import parse_media_uri

from tests.helpers import ids, make_video, media_auth, register

HLS = "/media/{}/hls/master.m3u8"
THUMB = "/media/{}/thumb.jpg"


def test_private_video_hidden_from_strangers_everywhere(new_client, fake):
    owner = register(new_client, "owner")
    stranger = register(new_client, "stranger")
    anon = new_client()
    vid = make_video(owner, fake, "Secret", visibility="private")

    for who in (anon, stranger.client):
        h = {}

        if who is stranger.client:
            h = stranger.h

        assert who.get(f"/api/videos/{vid}", headers=h).status_code == 404
        assert who.get(f"/api/videos/{vid}/comments", headers=h).status_code == 404
        assert media_auth(who, HLS.format(vid)).status_code == 403

    assert (
        media_auth(stranger.client, HLS.format(vid), stranger.media_token).status_code
        == 403
    )
    assert (
        stranger.client.post(
            f"/api/videos/{vid}/comments", headers=stranger.h, json={"text": "hi"}
        ).status_code
        == 404
    )
    assert (
        stranger.client.put(
            f"/api/videos/{vid}/like", headers=stranger.h, json={"value": 1}
        ).status_code
        == 404
    )
    assert (
        stranger.client.post(
            f"/api/videos/{vid}/report", headers=stranger.h, json={"reason": "spam"}
        ).status_code
        == 404
    )

    assert vid not in ids(anon.get("/api/feed"))
    assert vid not in ids(anon.get("/api/search", params={"q": "Secret"}))
    assert vid not in ids(anon.get("/api/channels/owner/videos"))
    assert vid not in ids(
        stranger.client.get("/api/channels/owner/videos", headers=stranger.h)
    )


def test_private_video_available_to_owner_shared_user_and_staff(new_client, fake):
    owner = register(new_client, "owner")
    friend = register(new_client, "friend")
    mod = register(new_client, "mod", role="moderator")
    vid = make_video(owner, fake, "Secret", visibility="private")

    assert owner.client.get(f"/api/videos/{vid}", headers=owner.h).status_code == 200
    assert (
        media_auth(owner.client, HLS.format(vid), owner.media_token).status_code == 200
    )
    assert mod.client.get(f"/api/videos/{vid}", headers=mod.h).status_code == 200
    assert friend.client.get(f"/api/videos/{vid}", headers=friend.h).status_code == 404

    assert (
        owner.client.post(
            f"/api/videos/{vid}/shares", headers=owner.h, json={"username": "friend"}
        ).status_code
        == 204
    )
    assert owner.client.get(f"/api/videos/{vid}/shares", headers=owner.h).json() == [
        "friend"
    ]
    assert friend.client.get(f"/api/videos/{vid}", headers=friend.h).status_code == 200
    r = media_auth(friend.client, HLS.format(vid), friend.media_token)
    assert r.status_code == 200 and "X-Amz-Signature" in r.headers["x-presigned-url"]
    assert vid in ids(owner.client.get("/api/channels/owner/videos", headers=owner.h))

    assert (
        owner.client.delete(
            f"/api/videos/{vid}/shares/friend", headers=owner.h
        ).status_code
        == 204
    )
    assert friend.client.get(f"/api/videos/{vid}", headers=friend.h).status_code == 404
    assert (
        media_auth(friend.client, HLS.format(vid), friend.media_token).status_code
        == 403
    )


def test_only_owner_manages_shares(new_client, fake):
    owner, other = register(new_client, "owner"), register(new_client, "other")
    vid = make_video(owner, fake, visibility="private")

    assert (
        other.client.post(
            f"/api/videos/{vid}/shares", headers=other.h, json={"username": "other"}
        ).status_code
        == 404
    )
    assert (
        owner.client.post(
            f"/api/videos/{vid}/shares", headers=owner.h, json={"username": "nobody"}
        ).status_code
        == 404
    )


def test_unlisted_reachable_by_link_but_not_listed(new_client, fake):
    owner = register(new_client, "owner")
    anon = new_client()
    vid = make_video(owner, fake, "Unlisted one", visibility="unlisted")

    assert anon.get(f"/api/videos/{vid}").status_code == 200
    assert media_auth(anon, HLS.format(vid)).status_code == 200
    assert vid not in ids(anon.get("/api/feed"))
    assert vid not in ids(anon.get("/api/search", params={"q": "Unlisted"}))
    assert vid not in ids(anon.get("/api/channels/owner/videos"))


def test_hidden_video_gone_from_feed_search_and_media(new_client, fake):
    owner = register(new_client, "owner")
    mod = register(new_client, "mod", role="moderator")
    anon = new_client()
    vid = make_video(owner, fake, "Bad video")

    assert vid in ids(anon.get("/api/feed"))
    assert (
        mod.client.post(
            f"/api/moderation/videos/{vid}/hide",
            headers=mod.h,
            json={"reason": "rules"},
        ).status_code
        == 204
    )
    assert vid not in ids(anon.get("/api/feed"))
    assert vid not in ids(anon.get("/api/search", params={"q": "Bad"}))
    assert vid not in ids(anon.get("/api/channels/owner/videos"))
    assert anon.get(f"/api/videos/{vid}").status_code == 404
    assert media_auth(anon, HLS.format(vid)).status_code == 403
    assert media_auth(anon, THUMB.format(vid)).status_code == 403
    assert (
        owner.client.get(f"/api/videos/{vid}", headers=owner.h).json()["is_hidden"]
        is True
    )
    assert media_auth(mod.client, HLS.format(vid), mod.media_token).status_code == 200
    assert (
        mod.client.post(
            f"/api/moderation/videos/{vid}/unhide", headers=mod.h
        ).status_code
        == 204
    )
    assert vid in ids(anon.get("/api/feed"))


def test_unprocessed_video_not_public(new_client, fake):
    owner, other = register(new_client, "owner"), register(new_client, "other")
    anon = new_client()
    vid = make_video(owner, fake, "Processing", ready=False)

    assert (
        owner.client.get(f"/api/videos/{vid}", headers=owner.h).json()["status"]
        == "processing"
    )
    assert anon.get(f"/api/videos/{vid}").status_code == 404
    assert other.client.get(f"/api/videos/{vid}", headers=other.h).status_code == 404
    assert vid not in ids(anon.get("/api/feed"))
    assert vid in ids(owner.client.get("/api/me/videos", headers=owner.h))


def test_media_auth_rejects_bad_tokens_and_paths(new_client, fake):
    owner = register(new_client, "owner")
    vid = make_video(owner, fake, visibility="private")
    anon = new_client()

    assert media_auth(anon, HLS.format(vid), "not-a-jwt").status_code == 403
    assert media_auth(anon, HLS.format(vid), owner.token).status_code == 403
    assert media_auth(anon, HLS.format(uuid.uuid4())).status_code == 403

    pub = make_video(owner, fake, "Pub")

    for bad in (
        f"/media/{pub}/source",
        f"/media/{pub}/hls/../source",
        f"/media/{pub}/../x/thumb.jpg",
        "/media/x/thumb.jpg",
        "",
    ):
        assert media_auth(anon, bad).status_code == 403, bad


def test_parse_media_uri():
    vid = uuid.uuid4()

    assert parse_media_uri(f"/media/{vid}/hls/360p/seg_00001.ts?x=1") == (
        vid,
        f"videos/{vid}/hls/360p/seg_00001.ts",
    )
    assert parse_media_uri(f"/media/{vid}/thumb.jpg")[1] == f"videos/{vid}/thumb.jpg"
    assert parse_media_uri(f"/media/{vid}/source") is None
    assert parse_media_uri(f"/media/{vid}/hls//etc") is None
