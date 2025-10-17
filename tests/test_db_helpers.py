from unittest.mock import patch, MagicMock

from linkedin.utils.db import get_db_url, update_answers_json


def test_get_db_url_from_env():
    with patch.dict('os.environ', {"DB_URL": "postgresql+psycopg2://u:p@h:5432/db"}, clear=False):
        assert get_db_url() == "postgresql+psycopg2://u:p@h:5432/db"


def test_update_answers_json_executes_sql():
    with patch('linkedin.db.create_engine') as eng_factory:
        mock_conn_ctx = MagicMock()
        mock_conn = MagicMock()
        mock_conn_ctx.__enter__.return_value = mock_conn
        eng = MagicMock()
        eng.begin.return_value = mock_conn_ctx
        eng_factory.return_value = eng

        with patch.dict('os.environ', {"DB_URL": "postgresql+psycopg2://u:p@h:5432/db"}, clear=False):
            ok = update_answers_json("123", '{"field": "value"}')
            assert ok is True
            assert mock_conn.execute.called
