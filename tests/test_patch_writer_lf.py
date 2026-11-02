"""The pinned Picard core diff must remain byte-identical on Windows."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

from compat import picard302_core_contract as core


class PatchWriterLineEndingTests(unittest.TestCase):
    def test_patch_writer_never_converts_lf_to_windows_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'picard302-test.patch'
            with patch.object(core,'read_checkout',return_value={}):
                with patch.object(core,'unified_patch',return_value='--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new\n'):
                    core.write_checkout_patch(Path(tmp),output)
            data=output.read_bytes()
            self.assertIn(b'@@ -1 +1 @@\n',data)
            self.assertNotIn(b'\r\n',data)
            self.assertEqual(data,b'--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new\n')


if __name__=='__main__':
    unittest.main()
