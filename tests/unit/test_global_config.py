import pytest
from sqlalchemy.orm import Session
from crud.common import get_global_config, set_global_config
from models.models import GlobalConfig


def test_set_and_get_global_config(db_session: Session):
    key = "TEST_KEY"
    value = "TEST_VALUE"

    # Ensure the key does not exist initially
    assert get_global_config(db_session, key) is None

    # Set the key-value pair
    set_global_config(db_session, key, value)

    # Verify the value is correctly set
    assert get_global_config(db_session, key) == value

    # Clean up
    db_session.query(GlobalConfig).filter(GlobalConfig.key == key).delete()
    db_session.commit()