from tests.helpers import ids, make_video, register


def test_plain_user_and_anon_cannot_moderate(new_client, fake):
    a = register(new_client, "alice")
    b = register(new_client, "bob")
    vid = make_video(a, fake)
    anon = new_client()

    for client, h, code in ((b.client, b.h, 403), (anon, {}, 401)):
        assert client.get("/api/moderation/reports", headers=h).status_code == code
        assert client.get("/api/moderation/hidden", headers=h).status_code == code
        assert (
            client.post(
                f"/api/moderation/videos/{vid}/hide", headers=h, json={}
            ).status_code
            == code
        )
        assert (
            client.post(f"/api/moderation/videos/{vid}/unhide", headers=h).status_code
            == code
        )

    assert ids(anon.get("/api/feed")) == [vid]


def test_moderator_cannot_manage_roles_or_users(new_client):
    m = register(new_client, "mod", role="moderator")
    u = register(new_client, "bob")

    assert (
        m.client.put(
            f"/api/admin/users/{u.id}/role", headers=m.h, json={"role": "admin"}
        ).status_code
        == 403
    )

    assert (
        m.client.put(
            f"/api/admin/users/{m.id}/role", headers=m.h, json={"role": "admin"}
        ).status_code
        == 403
    )

    assert m.client.get("/api/admin/users", headers=m.h).status_code == 403
    assert (
        u.client.put(
            f"/api/admin/users/{u.id}/role", headers=u.h, json={"role": "admin"}
        ).status_code
        == 403
    )


def test_admin_manages_roles(new_client):
    adm = register(new_client, "root", role="admin")
    u = register(new_client, "bob")
    r = adm.client.put(
        f"/api/admin/users/{u.id}/role", headers=adm.h, json={"role": "moderator"}
    )

    assert r.status_code == 200 and r.json()["role"] == "moderator"
    assert u.client.get("/api/moderation/reports", headers=u.h).status_code == 200

    assert (
        adm.client.put(
            f"/api/admin/users/{adm.id}/role", headers=adm.h, json={"role": "user"}
        ).status_code
        == 400
    )
    assert (
        adm.client.put(
            f"/api/admin/users/{u.id}/role", headers=adm.h, json={"role": "god"}
        ).status_code
        == 422
    )

    assert len(adm.client.get("/api/admin/users", headers=adm.h).json()) == 2
    assert (
        adm.client.put(
            f"/api/admin/users/{u.id}/active", headers=adm.h, json={"active": False}
        ).status_code
        == 200
    )
    assert u.client.get("/api/auth/me", headers=u.h).status_code == 401


def test_report_flow_and_resolution(new_client, fake):
    a = register(new_client, "alice")
    b = register(new_client, "bob")
    c = register(new_client, "carol")
    m = register(new_client, "mod", role="moderator")
    vid = make_video(a, fake, "Reported")

    assert (
        a.client.post(
            f"/api/videos/{vid}/report", headers=a.h, json={"reason": "mine"}
        ).status_code
        == 400
    )
    assert (
        b.client.post(
            f"/api/videos/{vid}/report", headers=b.h, json={"reason": "spam"}
        ).status_code
        == 201
    )

    assert (
        b.client.post(
            f"/api/videos/{vid}/report", headers=b.h, json={"reason": "spam"}
        ).status_code
        == 409
    )
    assert (
        c.client.post(
            f"/api/videos/{vid}/report", headers=c.h, json={"reason": "scam"}
        ).status_code
        == 201
    )
    assert b.client.post(
        f"/api/videos/{vid}/report", headers=b.h, json={"reason": "x"}
    ).status_code in (409, 422)

    reports = m.client.get("/api/moderation/reports", headers=m.h).json()

    assert len(reports) == 2 and {r["reporter"] for r in reports} == {"bob", "carol"}
    assert (
        m.client.post(
            f"/api/moderation/reports/{reports[0]['id']}/resolve",
            headers=m.h,
            json={"action": "hide"},
        ).status_code
        == 204
    )
    assert m.client.get("/api/moderation/reports", headers=m.h).json() == []
    assert (
        len(
            m.client.get(
                "/api/moderation/reports", headers=m.h, params={"status": "resolved"}
            ).json()
        )
        == 2
    )

    assert ids(m.client.get("/api/moderation/hidden", headers=m.h)) == [vid]
    assert new_client().get(f"/api/videos/{vid}").status_code == 404


def test_dismiss_keeps_video_visible(new_client, fake):
    a = register(new_client, "alice")
    b = register(new_client, "bob")
    m = register(new_client, "mod", role="moderator")
    vid = make_video(a, fake)

    b.client.post(f"/api/videos/{vid}/report", headers=b.h, json={"reason": "meh"})
    rid = m.client.get("/api/moderation/reports", headers=m.h).json()[0]["id"]

    assert (
        m.client.post(
            f"/api/moderation/reports/{rid}/resolve",
            headers=m.h,
            json={"action": "dismiss"},
        ).status_code
        == 204
    )

    assert new_client().get(f"/api/videos/{vid}").status_code == 200
    assert (
        m.client.post(
            "/api/moderation/reports/00000000-0000-0000-0000-000000000000/resolve",
            headers=m.h,
            json={"action": "dismiss"},
        ).status_code
        == 404
    )


def test_only_owner_or_admin_can_delete_video(new_client, fake):
    a = register(new_client, "alice")
    m = register(new_client, "mod", role="moderator")
    adm = register(new_client, "root", role="admin")
    vid = make_video(a, fake)

    assert m.client.delete(f"/api/videos/{vid}", headers=m.h).status_code == 404
    assert adm.client.delete(f"/api/videos/{vid}", headers=adm.h).status_code == 204
