from pyhive.api.hive_auth import HiveAuth
from pyhive.api.hive_api import HiveApi
import pyhive

def test_pyhive_exposes_sync_classes():
    assert pyhive.Auth is HiveAuth
    assert pyhive.API is HiveApi
