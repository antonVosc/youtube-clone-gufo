from tests.helpers import ids, make_video, register


def test_like_is_idempotent_and_switchable(new_client, fake):
    a = register(new_client, "alice")
    b = register(new_client, "bob")
    vid = make_video(a, fake)
    url = f"/api/videos/{vid}/like"

    for _ in range(3):
        r = b.client.put(url, headers=b.h, json={"value": 1})

        assert r.json() == {"likes": 1, "dislikes": 0, "my_like": 1}

    assert b.client.put(url, headers=b.h, json={"value": -1}).json() == {
        "likes": 0,
        "dislikes": 1,
        "my_like": -1,
    }
    assert a.client.put(url, headers=a.h, json={"value": 1}).json() == {
        "likes": 1,
        "dislikes": 1,
        "my_like": 1,
    }
    assert b.client.put(url, headers=b.h, json={"value": 0}).json() == {
        "likes": 1,
        "dislikes": 0,
        "my_like": 0,
    }
    assert b.client.put(url, headers=b.h, json={"value": 5}).status_code == 422
    assert new_client().put(url, json={"value": 1}).status_code == 401
    assert new_client().get(f"/api/videos/{vid}").json()["likes"] == 1


def test_comments_create_list_reply_validate(new_client, fake):
    a = register(new_client, "alice")
    b = register(new_client, "bob")
    vid = make_video(a, fake)

    c1 = b.client.post(
        f"/api/videos/{vid}/comments", headers=b.h, json={"text": "  hello <b>x</b>  "}
    )
    c2 = a.client.post(
        f"/api/videos/{vid}/comments",
        headers=a.h,
        json={"text": "re", "parent_id": c1.json()["id"]},
    )

    lst = new_client().get(f"/api/videos/{vid}/comments").json()

    assert (
        c1.status_code == 201
        and c1.json()["text"] == "hello <b>x</b>"
        and c1.json()["username"] == "bob"
    )
    assert c2.json()["parent_id"] == c1.json()["id"]
    assert [c["text"] for c in lst] == ["re", "hello <b>x</b>"]
    assert (
        b.client.post(
            f"/api/videos/{vid}/comments", headers=b.h, json={"text": "   "}
        ).status_code
        == 422
    )
    assert (
        b.client.post(
            f"/api/videos/{vid}/comments", headers=b.h, json={"text": "x" * 2001}
        ).status_code
        == 422
    )
    assert (
        new_client()
        .post(f"/api/videos/{vid}/comments", json={"text": "hi"})
        .status_code
        == 401
    )
    other = make_video(a, fake, "Other")
    assert (
        b.client.post(
            f"/api/videos/{other}/comments",
            headers=b.h,
            json={"text": "x", "parent_id": c1.json()["id"]},
        ).status_code
        == 404
    )


def test_comment_delete_rights(new_client, fake):
    a = register(new_client, "alice")
    b = register(new_client, "bob")
    m = register(new_client, "mod", role="moderator")

    vid = make_video(a, fake)
    cid = b.client.post(
        f"/api/videos/{vid}/comments", headers=b.h, json={"text": "mine"}
    ).json()["id"]
    cid2 = b.client.post(
        f"/api/videos/{vid}/comments", headers=b.h, json={"text": "again"}
    ).json()["id"]

    assert a.client.delete(f"/api/comments/{cid}", headers=a.h).status_code == 403
    assert m.client.delete(f"/api/comments/{cid}", headers=m.h).status_code == 204
    assert b.client.delete(f"/api/comments/{cid2}", headers=b.h).status_code == 204
    assert b.client.delete(f"/api/comments/{cid2}", headers=b.h).status_code == 404


def test_view_counter(new_client, fake):
    a = register(new_client, "alice")
    vid = make_video(a, fake)
    anon = new_client()

    assert anon.post(f"/api/videos/{vid}/view").status_code == 204
    assert anon.post(f"/api/videos/{vid}/view").status_code == 204
    assert anon.get(f"/api/videos/{vid}").json()["views_count"] == 2


def test_subscribe_flow(new_client, fake):
    a = register(new_client, "alice")
    b = register(new_client, "bob")
    vid = make_video(a, fake, "From alice")

    make_video(b, fake, "From bob")
    assert b.client.get("/api/feed/subscriptions", headers=b.h).json() == []

    for _ in range(2):
        r = b.client.post("/api/channels/alice/subscribe", headers=b.h)
        assert r.json()["subscribers"] == 1 and r.json()["subscribed"] is True

    assert ids(b.client.get("/api/feed/subscriptions", headers=b.h)) == [vid]
    assert new_client().get("/api/channels/alice").json()["subscribed"] is False
    assert (
        a.client.post("/api/channels/alice/subscribe", headers=a.h).status_code == 400
    )
    assert (
        b.client.delete("/api/channels/alice/subscribe", headers=b.h).json()[
            "subscribers"
        ]
        == 0
    )
    assert (
        b.client.post("/api/channels/nobody/subscribe", headers=b.h).status_code == 404
    )
    assert new_client().get("/api/feed/subscriptions").status_code == 401


def test_playlists(new_client, fake):
    a = register(new_client, "alice")
    b = register(new_client, "bob")
    m = register(new_client, "mod", role="moderator")

    v1 = make_video(a, fake, "One")
    v2 = make_video(a, fake, "Two")
    pl = a.client.post("/api/playlists", headers=a.h, json={"title": "Best"}).json()[
        "id"
    ]

    for v in (v1, v2, v1):
        assert (
            a.client.post(
                f"/api/playlists/{pl}/items", headers=a.h, json={"video_id": v}
            ).status_code
            == 200
        )

    assert ids_of(new_client().get(f"/api/playlists/{pl}")) == [v1, v2]
    assert (
        b.client.post(
            f"/api/playlists/{pl}/items", headers=b.h, json={"video_id": v1}
        ).status_code
        == 404
    )

    m.client.post(f"/api/moderation/videos/{v2}/hide", headers=m.h, json={})
    assert ids_of(new_client().get(f"/api/playlists/{pl}")) == [v1]
    assert [
        p["title"] for p in new_client().get("/api/channels/alice/playlists").json()
    ] == ["Best"]

    priv = a.client.post(
        "/api/playlists", headers=a.h, json={"title": "Mine", "visibility": "private"}
    ).json()["id"]
    assert new_client().get(f"/api/playlists/{priv}").status_code == 404
    assert len(new_client().get("/api/channels/alice/playlists").json()) == 1
    assert (
        a.client.delete(f"/api/playlists/{pl}/items/{v1}", headers=a.h).status_code
        == 204
    )
    assert a.client.delete(f"/api/playlists/{pl}", headers=a.h).status_code == 204


def ids_of(resp):
    return [v["id"] for v in resp.json()["videos"]]


def test_search_and_feed(new_client, fake):
    a = register(new_client, "alice")
    cats = make_video(a, fake, "Funny Cats Compilation")
    make_video(a, fake, "Python tutorial")
    anon = new_client()

    assert ids(anon.get("/api/search", params={"q": "cats"})) == [cats]
    assert ids(anon.get("/api/search", params={"q": "ats"})) == [cats]
    assert anon.get("/api/search", params={"q": "100%_"}).json() == []
    assert anon.get("/api/search", params={"q": ""}).status_code == 422

    feed = anon.get("/api/feed").json()
    assert [v["title"] for v in feed] == ["Python tutorial", "Funny Cats Compilation"]
    assert len(anon.get("/api/feed", params={"limit": 1, "offset": 1}).json()) == 1
    assert anon.get("/api/feed", params={"limit": 500}).status_code == 422
