import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import public_data as p


class PublicDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name) / 'reads'
        self.manifest = json.loads(p.MANIFEST.read_text())
        self.payloads = []
        for mate, item in enumerate(self.manifest['files'], 1):
            data = gzip.compress(f'@toy/{mate}\nACGT\n+\nIIII\n'.encode(), mtime=0)
            self.payloads.append(data)
            item.update(bytes=len(data), md5=hashlib.md5(data).hexdigest(), sha256=hashlib.sha256(data).hexdigest())

    def download(self, **kwargs):
        streams = iter(self.payloads)
        return p.download(self.manifest, self.dest, allow_network=True,
                          opener=lambda url: io.BytesIO(next(streams)), reserve=0, **kwargs)

    def test_no_consent_has_no_network_or_write(self):
        with self.assertRaisesRegex(ValueError, 'allow-network'):
            p.download(self.manifest, self.dest)
        self.assertFalse(self.dest.exists())

    def test_malformed_manifest_entry_is_explained(self):
        self.manifest['files'][0] = None
        with self.assertRaises(ValueError):
            p.download(self.manifest, self.dest, allow_network=True)
        self.assertFalse(self.dest.exists())

    def test_network_error_retains_inspectable_partial(self):
        def failure(url):
            raise OSError('network interrupted')
        with self.assertRaises(OSError):
            p.download(self.manifest, self.dest, allow_network=True, reserve=0, opener=failure)
        self.assertEqual(len(list(self.dest.glob('*.part'))), 1)

    def test_redirect_is_rejected(self):
        with self.assertRaises(ValueError):
            p.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example')

    def test_gzip_crc_corruption_detected_even_with_matching_file_hash(self):
        self.payloads[0] = self.payloads[0][:-8] + b'\x00' * 8
        item = self.manifest['files'][0]
        item.update(bytes=len(self.payloads[0]), md5=hashlib.md5(self.payloads[0]).hexdigest(), sha256=hashlib.sha256(self.payloads[0]).hexdigest())
        self.download()
        with self.assertRaises((OSError, ValueError)):
            p.verify(self.manifest, self.dest)

    def test_empty_fastq_identifier_is_explained(self):
        for header in (b'@', b'@   '):
            with self.subTest(header=header):
                with self.assertRaisesRegex(ValueError, 'identifier'):
                    p.fastq_record(io.BytesIO(header + b'\nACGT\n+\nIIII\n'))

    def test_streamed_download_and_complete_fastq_verification(self):
        self.download()
        self.assertEqual(p.verify(self.manifest, self.dest)['read_pairs'], 1)
        with self.assertRaises(FileExistsError):
            self.download()

    def test_invalid_manifest_rejected_before_destination_creation(self):
        for key, value in [('name', '../escape.gz'), ('url', 'http://ftp.sra.ebi.ac.uk/x'),
                           ('url', 'https://evil.example/reads'), ('md5', 'x'), ('bytes', -1)]:
            with self.subTest(key=key, value=value):
                m = copy.deepcopy(self.manifest)
                m['files'][0][key] = value
                with self.assertRaises(ValueError):
                    p.download(m, self.dest, allow_network=True)
                self.assertFalse(self.dest.exists())

    def test_caps_and_space_checked_before_network(self):
        with self.assertRaisesRegex(ValueError, 'cap'):
            self.download(byte_cap=1)
        with patch.object(p.shutil, 'disk_usage', return_value=(100, 100, 0)):
            with self.assertRaisesRegex(ValueError, 'space'):
                self.download()

    def test_bad_hash_and_oversize_preserve_partial(self):
        self.manifest['files'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.download()
        self.assertEqual((self.dest / (self.manifest['files'][0]['name'] + '.part')).read_bytes(), self.payloads[0])
        with self.assertRaises(FileExistsError):
            self.download()

    def test_oversized_stream_stops_and_keeps_partial(self):
        self.manifest['files'][0]['bytes'] = 1
        with self.assertRaisesRegex(ValueError, 'size'):
            self.download()
        self.assertTrue(list(self.dest.glob('*.part')))

    def test_symlink_destination_and_existing_second_file_refused(self):
        target = Path(self.tmp.name) / 'target'
        target.mkdir()
        try:
            self.dest.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest('OS does not permit unprivileged symlinks')
        with self.assertRaises(ValueError):
            self.download()
        self.assertEqual(list(target.iterdir()), [])

    def test_existing_second_file_preserved_before_any_transfer(self):
        self.dest.mkdir()
        second = self.dest / self.manifest['files'][1]['name']
        second.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            self.download()
        self.assertEqual(list(self.dest.iterdir()), [second])
        self.assertEqual(second.read_bytes(), b'keep')

    def test_matching_hashes_do_not_hide_invalid_gzip_or_pairing(self):
        self.payloads[1] = gzip.compress(b'@different/2\nACGT\n+\nIIII\n', mtime=0)
        item = self.manifest['files'][1]
        item.update(bytes=len(self.payloads[1]), md5=hashlib.md5(self.payloads[1]).hexdigest(), sha256=hashlib.sha256(self.payloads[1]).hexdigest())
        self.download()
        with self.assertRaisesRegex(ValueError, 'pair'):
            p.verify(self.manifest, self.dest)


if __name__ == '__main__':
    unittest.main()
