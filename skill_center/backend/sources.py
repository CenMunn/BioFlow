"""Public GitHub snapshot resolver. No repository code is executed."""
import re
from urllib.parse import quote, unquote, urlparse

import httpx

from .packages import Fault, MAX_UPLOAD, relative

ALLOWED_HOSTS = {'api.github.com', 'codeload.github.com', 'github.com'}


def fetch(url, binary=False, cancel=lambda: False):
    if urlparse(url).scheme != 'https' or urlparse(url).hostname not in ALLOWED_HOSTS:
        raise Fault('SOURCE_UNAVAILABLE','不允许访问该下载来源。')
    try:
        with httpx.Client(timeout=httpx.Timeout(30, read=60), follow_redirects=False, headers={'User-Agent':'BioFlow-Skill-Center/1.0','Accept':'application/vnd.github+json'}) as client:
            for _ in range(4):
                with client.stream('GET',url) as response:
                    if response.is_redirect:
                        location = response.headers.get('location','')
                        parsed = urlparse(location)
                        if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
                            raise Fault('SOURCE_UNAVAILABLE','下载重定向到不支持的来源。')
                        url = location
                        continue
                    if response.status_code == 404 or (response.status_code == 422 and '/commits/' in url):
                        raise Fault('SOURCE_NOT_FOUND','仓库、版本或路径不存在。',404)
                    if response.status_code in {403,429}:
                        raise Fault('SOURCE_UNAVAILABLE','GitHub 限流或拒绝访问，请稍后重试或上传 ZIP。',502)
                    response.raise_for_status()
                    chunks, total = [], 0
                    limit = MAX_UPLOAD if binary else 8 * 1024 * 1024
                    for chunk in response.iter_bytes():
                        if cancel():
                            raise Fault('IMPORT_CANCELLED','导入已取消。')
                        total += len(chunk)
                        if total > limit:
                            raise Fault('IMPORT_LIMIT_EXCEEDED','GitHub 下载超过大小限额。',413)
                        chunks.append(chunk)
                    content = b''.join(chunks)
                    if binary:
                        return content
                    return __import__('json').loads(content)
            raise Fault('SOURCE_UNAVAILABLE','GitHub 下载重定向次数过多。',502)
    except (httpx.HTTPError, ValueError) as exc:
        raise Fault('SOURCE_UNAVAILABLE','无法获取 GitHub 来源，请重试或上传 ZIP。',502,{'reason':str(exc)[:240]})


def resolve(url, explicit_ref=None, explicit_path=None):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'github.com' or parsed.username or parsed.password or parsed.query:
        raise Fault('INVALID_SOURCE','请输入公开 github.com 仓库、tree 目录或 blob/SKILL.md 链接。')
    parts = [unquote(x) for x in parsed.path.strip('/').split('/')]
    if len(parts)<2 or not re.fullmatch(r'[A-Za-z0-9_.-]+',parts[0]) or not re.fullmatch(r'[A-Za-z0-9_.-]+',parts[1]):
        raise Fault('INVALID_SOURCE','GitHub 仓库地址无效。')
    owner, repo = parts[0],parts[1].removesuffix('.git')
    base = f'https://api.github.com/repos/{owner}/{repo}'
    info = fetch(base)
    if info.get('private'):
        raise Fault('INVALID_SOURCE','首期只支持公开仓库。')
    path = explicit_path or ''
    ref = explicit_ref
    sha = None
    if ref:
        sha = fetch(base+'/commits/'+quote(ref,safe=''))['sha']
    elif len(parts)==2:
        ref = info['default_branch']
        sha = fetch(base+'/commits/'+quote(ref,safe=''))['sha']
    elif len(parts)>=4 and parts[2] in {'tree','blob'}:
        tail = parts[3:]
        choices = []
        for length in range(min(len(tail),12),0,-1):
            candidate = '/'.join(tail[:length])
            try:
                commit = fetch(base+'/commits/'+quote(candidate,safe=''))
                choices.append((candidate,commit['sha'],'/'.join(tail[length:])))
            except Fault as exc:
                if exc.code != 'SOURCE_NOT_FOUND':
                    raise
        if len(choices)!=1:
            raise Fault('AMBIGUOUS_REF','版本无法唯一确认，请填写明确分支和技能路径。',details={'candidates':[x[0] for x in choices]})
        ref,sha,path = choices[0]
        if parts[2]=='blob' and not path.endswith('SKILL.md'):
            raise Fault('INVALID_SOURCE','blob 链接必须指向 SKILL.md。')
    else:
        raise Fault('INVALID_SOURCE','不支持的 GitHub 链接类型。')
    if path:
        path = relative(path)
    return {'repository_url':f'https://github.com/{owner}/{repo}','owner':owner,'repo':repo,'ref':ref,'commit_sha':sha,'requested_path':path,'license':(info.get('license') or {}).get('spdx_id')}


def download(source, cancel=lambda: False):
    return fetch(f"https://codeload.github.com/{source['owner']}/{source['repo']}/zip/{source['commit_sha']}",binary=True,cancel=cancel)


def links(source, entry):
    prefix=source.get('package_prefix')
    if prefix and entry.startswith(prefix+'/'):
        entry=entry[len(prefix)+1:]
    path = str(__import__('pathlib').PurePosixPath(entry).parent)
    if path=='.':
        path=''
    suffix = '/'+quote(path,safe='/') if path else ''
    return {'original':f"{source['repository_url']}/tree/{quote(source['ref'],safe='')}{suffix}",'imported':f"{source['repository_url']}/tree/{source['commit_sha']}{suffix}",'latest':f"{source['repository_url']}/tree/{quote(source['ref'],safe='')}{suffix}"}
