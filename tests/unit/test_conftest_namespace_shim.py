# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import atexit
import shutil


def test_namespace_shim_registers_working_cleanup(namespace_shim_factory, monkeypatch, tmp_path):
    # No import of conftest at all, bare or qualified -- pytest injects
    # _create_namespace_shim via the namespace_shim_factory fixture
    # (defined in conftest.py itself), sidestepping the sys.path/package-
    # resolution question entirely rather than picking a side of it.
    registered = []
    monkeypatch.setattr(atexit, "register", lambda fn, *args, **kwargs: registered.append((fn, args, kwargs)))

    result = namespace_shim_factory("test_shim_", "llama", tmp_path)
    try:
        assert result.exists()
        assert len(registered) == 1
        fn, args, kwargs = registered[0]

        # Regression check: it's not enough that *something* was registered --
        # invoking exactly what was registered must actually remove the
        # directory. This is what catches a wrong path, wrong function, or a
        # missing atexit.register call entirely.
        fn(*args, **kwargs)
        assert not result.exists()
    finally:
        # monkeypatching atexit.register above means the real cleanup this
        # fix adds never actually gets registered for this test's own
        # directory -- without this, a failed assertion above would leak
        # exactly the kind of directory this whole fix exists to stop
        # leaking.
        shutil.rmtree(str(result), ignore_errors=True)
