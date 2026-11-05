"""Opt-in ENA download and bounded streaming verification; standard library only."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name('public-data.json')
CHUNK = 1024 * 1024


def safe_path(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink paths are not allowed')
    return path


def validate(manifest):
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1 or manifest.get('accession') != 'SRR9224248':
        raise ValueError('Unsupported manifest/accession')
    files = manifest.get('files')
    if not isinstance(files, list) or len(files) != 2:
        raise ValueError('Exactly two paired files required')
    for mate, item in enumerate(files, 1):
        if not isinstance(item, dict):
            raise ValueError('Manifest file entry must be an object')
        name = f'SRR9224248_{mate}.fastq.gz'
        url = 'https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR922/008/SRR9224248/' + name
        if item.get('name') != name or item.get('url') != url:
            raise ValueError('Only the pinned HTTPS ENA file paths are allowed')
        if type(item.get('bytes')) is not int or not 0 < item['bytes'] <= 2 * 1024**3:
            raise ValueError('Invalid compressed size')
        for algorithm, length in [('md5', 32), ('sha256', 64)]:
            if not isinstance(item.get(algorithm), str) or not re.fullmatch('[0-9a-f]{' + str(length) + '}', item[algorithm]):
                raise ValueError('Invalid hash')
    return files


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused; inspect official ENA provenance manually')


def network_open(url):
    # Default TLS verification retained; no credentials or environment proxies.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(url, timeout=60)


def transfer(source, target, item):
    digests = {key: hashlib.new(key) for key in ('md5', 'sha256')}
    size = 0
    while True:
        block = source.read(CHUNK)
        if not block:
            break
        size += len(block)
        if target is not None:
            target.write(block)
        if size > item['bytes']:
            raise ValueError('Compressed size exceeded; partial retained')
        for digest in digests.values():
            digest.update(block)
    if size != item['bytes'] or any(d.hexdigest() != item[k] for k, d in digests.items()):
        raise ValueError('File integrity/size mismatch; partial retained')


def download(manifest, dest, *, allow_network=False, byte_cap=2 * 1024**3,
             reserve=1024**3, opener=None):
    files = validate(manifest)
    if not allow_network:
        raise ValueError('Download requires --allow-network; plan is offline')
    dest = safe_path(dest)
    total = sum(item['bytes'] for item in files)
    if total > byte_cap or byte_cap <= 0 or reserve < 0:
        raise ValueError('Download exceeds byte cap or invalid reserve')
    for item in files:
        for suffix in ('', '.part'):
            path = safe_path(dest / (item['name'] + suffix))
            if path.exists():
                raise FileExistsError('Existing file/partial preserved; inspect and manually choose a new destination')
    ancestor = dest
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor)[2] < total + reserve:
        raise ValueError('Insufficient free disk space including reserve')
    dest.mkdir(parents=True, exist_ok=True)
    for item in files:
        final = safe_path(dest / item['name'])
        partial = safe_path(dest / (item['name'] + '.part'))
        with partial.open('xb') as target:
            with (opener or network_open)(item['url']) as source:
                transfer(source, target, item)
        # Hard-link publication is exclusive: never overwrite a file appearing mid-download.
        import os
        os.link(partial, final)
        partial.unlink()
    return {'downloaded': len(files), 'compressed_bytes': total}


def fastq_record(stream):
    lines = [stream.readline(CHUNK + 1) for _ in range(4)]
    if not any(lines):
        return None
    if any(not line.endswith(b'\n') or len(line) > CHUNK for line in lines):
        raise ValueError('Truncated or excessive FASTQ record')
    header, sequence, plus, quality = [line.rstrip(b'\r\n') for line in lines]
    if not header.startswith(b'@') or not plus.startswith(b'+') or not sequence or len(sequence) != len(quality):
        raise ValueError('Invalid FASTQ structure')
    if not re.fullmatch(b'[ACGTNacgtn]+', sequence) or any(c < 33 or c > 126 for c in quality):
        raise ValueError('Invalid FASTQ sequence/quality')
    identifiers = header[1:].split()
    if not identifiers:
        raise ValueError('Missing FASTQ identifier')
    return identifiers[0]


def verify(manifest, dest):
    files = validate(manifest)
    dest = safe_path(dest)
    for item in files:
        with safe_path(dest / item['name']).open('rb') as source:
            transfer(source, None, item)
    count = 0
    with gzip.open(dest / files[0]['name'], 'rb') as one, gzip.open(dest / files[1]['name'], 'rb') as two:
        while True:
            a, b = fastq_record(one), fastq_record(two)
            if a is None and b is None:
                break
            if a is None or b is None or a.removesuffix(b'/1') != b.removesuffix(b'/2'):
                raise ValueError('FASTQ pair identifiers/count mismatch')
            count += 1
    if not count:
        raise ValueError('Empty paired FASTQ')
    return {'integrity': 'MD5 + SHA256 + complete gzip CRC and paired FASTQ passed', 'read_pairs': count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'download', 'verify'])
    parser.add_argument('--dest', type=Path, default=ROOT / 'runtime/reproduction/public-data')
    parser.add_argument('--allow-network', action='store_true', help='Explicit consent for approximately 1.09 GB ENA download')
    parser.add_argument('--byte-cap', type=int, default=2 * 1024**3)
    parser.add_argument('--disk-reserve', type=int, default=1024**3)
    args = parser.parse_args()
    try:
        manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
        files = validate(manifest)
        if args.action == 'plan':
            result = {'network': False, 'compressed_bytes': sum(f['bytes'] for f in files), 'destination': str(args.dest), 'manifest': manifest}
        elif args.action == 'download':
            result = download(manifest, args.dest, allow_network=args.allow_network, byte_cap=args.byte_cap, reserve=args.disk_reserve)
        else:
            result = verify(manifest, args.dest)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, EOFError, KeyError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
