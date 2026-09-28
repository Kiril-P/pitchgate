from pitchgate import create_app


def test_home_creates_sqlite_file(tmp_path):
    db_path = tmp_path / "pitchgate.sqlite"
    app = create_app(
        {
            "DATA_DIR": tmp_path,
            "DATABASE": db_path,
            "PORT": 5000,
        }
    )

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"Pitchgate" in response.data
    assert db_path.is_file()
