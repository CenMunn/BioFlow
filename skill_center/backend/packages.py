"""Byte-preserving bundles, bounded extraction and Agent Skills diagnostics."""
import hashlib
import io
import json
import mimetypes
import os
import posixpath
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

import yaml

MAX_UPLOAD = int(os.getenv('SC_MAX_UPLOAD', 50 * 1024 * 1024))
MAX_EXTRACT = int(os.getenv('SC_MAX_EXTRACT', 200 * 1024 * 1024))
MAX_FILES = int(os.getenv('SC_MAX_FILES', 5000))
MAX_DEPTH = int(os.getenv('SC_MAX_DEPTH', 8))
MAX_PREVIEW = 2 * 1024 * 1024
EXPORT_MANIFEST = '.bioflow-export.json'
NAME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


class Fault(Exception):
    def __init__(self, code, message, status=400, details=None):
        self.code, self.message, self.status, self.details = code, message, status, details or {}


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise Fault('INVALID_PATH', '文件路径无效。')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or any(':' in x or x in {'', '.'} for x in p.parts):
        raise Fault('INVALID_PATH', '文件路径不能越过技能包边界。')
    return p.as_posix()


def safe(root, value):
    value = relative(value)
    root = Path(root).resolve()
    p = root / value
    if not p.resolve().is_relative_to(root) or any(x.is_symlink() for x in [p, *p.parents] if x != root.parent):
        raise Fault('INVALID_PATH', '不允许符号链接或越界路径。')
    return p


def files(root):
    result, total = [], 0
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink():
            raise Fault('INVALID_PATH', '技能包不能包含符号链接。')
        if not p.is_file():
            continue
        name = p.relative_to(root).as_posix()
        if name == EXPORT_MANIFEST:
            continue
        if len(PurePosixPath(name).parts) > MAX_DEPTH:
            raise Fault('IMPORT_LIMIT_EXCEEDED', f'目录深度超过 {MAX_DEPTH} 层。')
        size = p.stat().st_size
        total += size
        if len(result) >= MAX_FILES or total > MAX_EXTRACT:
            raise Fault('IMPORT_LIMIT_EXCEEDED', '文件数量或解压总大小超过限额。')
        mime = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        preview = size <= MAX_PREVIEW and ('text' in mime or p.suffix.lower() in {'.md','.py','.r','.sh','.yaml','.yml','.json','.csv','.ts','.js','.toml','.txt','.xml','.svg'})
        result.append({'path': name, 'size': size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'mime_type': mime, 'preview_support': preview})
    return result


def content_hash(manifest):
    digest = hashlib.sha256()
    for f in sorted(manifest, key=lambda x: x['path']):
        digest.update(f['path'].encode() + b'\0' + f['sha256'].encode() + b'\n')
    return digest.hexdigest()


def metadata(raw):
    if len(raw)>MAX_PREVIEW:
        raise Fault('INVALID_SKILL_FORMAT','SKILL.md 超过可解析大小，请拆分参考资料。')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise Fault('INVALID_SKILL_FORMAT', 'SKILL.md 必须使用 UTF-8 编码；原始字节仍可保存阅读。')
    match = re.match(r'^---\s*\r?\n(.*?)\r?\n---(?:\s*\r?\n|$)', text, re.S)
    if not match:
        raise Fault('INVALID_SKILL_FORMAT', '缺少 YAML 元数据（---）。')
    class BoundedLoader(yaml.SafeLoader):
        def compose_node(self, parent, index):
            if self.check_event(yaml.AliasEvent):
                raise yaml.YAMLError('YAML aliases are not supported by the preview parser')
            return super().compose_node(parent,index)
    try:
        fields = yaml.load(match[1], Loader=BoundedLoader)
    except yaml.YAMLError as exc:
        raise Fault('INVALID_SKILL_FORMAT', 'YAML 格式错误。', details={'reason': str(exc)[:300]})
    if not isinstance(fields, dict):
        raise Fault('INVALID_SKILL_FORMAT', 'YAML 元数据必须是对象。')
    return fields, text[match.end():], text


def diagnose(root, entry):
    entry = relative(entry)
    errors, warnings, missing, unresolved = [], [], [], []
    meta, body = {}, ''
    if not safe(root, entry).is_file():
        return {'format_status': 'invalid', 'errors': ['缺少 SKILL.md'], 'warnings': [], 'resource_status': 'unknown', 'missing_paths': [], 'unconfirmed_references': [], 'metadata': {}}
    try:
        meta, body, _ = metadata(safe(root, entry).read_bytes())
    except Fault as exc:
        errors.append(exc.message)
    name, description = meta.get('name'), meta.get('description')
    if not isinstance(name, str) or len(name) > 64 or not NAME.fullmatch(name):
        errors.append('name 必须为 1～64 字符的小写字母、数字和单连字符。')
    elif PurePosixPath(entry).parent.name != name:
        errors.append('name 必须与技能入口的父目录名一致。')
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        errors.append('description 必须为非空字符串，最长 1024 字符。')
    if 'compatibility' in meta and (not isinstance(meta['compatibility'], str) or not 1 <= len(meta['compatibility']) <= 500):
        errors.append('compatibility 必须为 1～500 字符。')
    if 'metadata' in meta and (not isinstance(meta['metadata'], dict) or any(not isinstance(k, str) or not isinstance(v, str) for k,v in meta['metadata'].items())):
        errors.append('metadata 必须为字符串到字符串的映射。')
    for key in ('license', 'allowed-tools'):
        if key in meta and not isinstance(meta[key], str):
            errors.append(f'{key} 必须为字符串。')
    if len(body.splitlines()) > 500:
        warnings.append('正文超过 500 行，建议将参考内容拆到资源文件。')
    refs = re.findall(r'\]\(([^\s)]+)(?:\s+[^)]*)?\)', body)
    refs += re.findall(r'(?<![\w/])((?:\.\./)*(?:references|scripts|assets|templates|static)/[\w./-]+\.[\w]+)', body)
    for ref in sorted(set(refs)):
        if ref.startswith(('#','https:','http:','mailto:')):
            continue
        ref = ref.split('#')[0]
        target = posixpath.normpath(posixpath.join(str(PurePosixPath(entry).parent), ref))
        if not target or target.startswith('../') or target.startswith('/'):
            unresolved.append(ref)
        elif not safe(root, target).exists():
            missing.append(target)
    if missing:
        warnings.append('存在缺失的相对引用资源。')
    if unresolved:
        warnings.append('存在越出当前包边界的引用，需要确认共享依赖。')
    display_meta=json.loads(json.dumps(meta, default=str))
    return {'format_status': 'invalid' if errors else ('warnings' if warnings else 'valid'), 'errors': errors, 'warnings': warnings, 'resource_status': 'incomplete' if missing else ('unknown' if unresolved else 'complete'), 'missing_paths': missing, 'unconfirmed_references': unresolved, 'metadata': display_meta, 'reference_detection': '基于正文相对链接及常见资源路径；动态脚本依赖未自动确认。'}


def extract_zip(data, destination, strip_repository_root=False, allowed_paths=None):
    if len(data) > MAX_UPLOAD:
        raise Fault('IMPORT_LIMIT_EXCEEDED', '上传或下载超过压缩大小限额。', 413)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise Fault('INVALID_ARCHIVE', '无法识别 ZIP 压缩包。')
    entries = archive.infolist()
    if len(entries) > (50000 if allowed_paths is not None else MAX_FILES):
        raise Fault('IMPORT_LIMIT_EXCEEDED', '压缩包条目数超过限额。', 413)
    total, paths = 0, set()
    for info in entries:
        name = relative(info.filename.rstrip('/'))
        if strip_repository_root:
            parts = PurePosixPath(name).parts
            if len(parts) == 1:
                continue
            name = '/'.join(parts[1:])
        if allowed_paths is not None and name not in allowed_paths:
            continue
        if len(paths)>=MAX_FILES:
            raise Fault('IMPORT_LIMIT_EXCEEDED','所选资源文件数量超过限额。',413)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR):
            raise Fault('INVALID_ARCHIVE', '压缩包包含链接或特殊文件。')
        if info.flag_bits & 1:
            raise Fault('INVALID_ARCHIVE', '不支持加密 ZIP。')
        if name in paths:
            raise Fault('INVALID_ARCHIVE', '压缩包包含重复路径。')
        paths.add(name)
        total += info.file_size
        if total > MAX_EXTRACT or len(PurePosixPath(name).parts) > MAX_DEPTH:
            raise Fault('IMPORT_LIMIT_EXCEEDED', '解压大小或目录深度超过限额。', 413)
        target = safe(destination, name)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open('wb') as out:
                remaining = info.file_size
                while True:
                    chunk = source.read(65536)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise Fault('INVALID_ARCHIVE', 'ZIP 文件大小与声明不符。')
                    out.write(chunk)
    return files(destination)


def scan(root, prefix=''):
    all_files = files(root)
    candidates = []
    for f in all_files:
        path = f['path']
        if PurePosixPath(path).name != 'SKILL.md':
            continue
        if prefix and not (path == prefix or path.startswith(prefix.rstrip('/') + '/')):
            continue
        d = diagnose(root, path)
        name=d['metadata'].get('name'); description=d['metadata'].get('description')
        candidates.append({'entry_path': path, 'skill_name': name if isinstance(name,str) else PurePosixPath(path).parent.name, 'description': description if isinstance(description,str) else '', 'diagnostics': d, 'files': [x for x in all_files if x['path'].startswith(str(PurePosixPath(path).parent) + '/') or path == 'SKILL.md']})
    return candidates, all_files


def copy_selection(source, target, entry, support_paths=()):
    entry = relative(entry)
    parent = str(PurePosixPath(entry).parent)
    prefixes = [parent] + [relative(x) for x in support_paths]
    selected = []
    for f in files(source):
        p = f['path']
        license_file = PurePosixPath(p).name.lower().startswith(('license','copying','notice')) and '/' not in p
        if license_file or any(x == '.' or p == x or p.startswith(x.rstrip('/')+'/') for x in prefixes):
            selected.append(p)
    if entry not in selected:
        raise Fault('INVALID_SELECTION', '所选入口不属于扫描结果。')
    for p in selected:
        dst = safe(target,p)
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(safe(source,p), dst)
    return files(target)


def export_zip(root, manifest):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for f in files(root):
            archive.write(safe(root,f['path']), f['path'])
        archive.writestr(EXPORT_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
    return out.getvalue()


TEMPLATES = {
 'blank': '# 用途\n\n## 触发条件\n\n## 输入\n\n## 步骤\n1. 理解用户任务。\n\n## 输出\n\n## 约束\n保留事实，不编造数据。\n\n## 检查\n\n## 示例\n\n## 资源引用\n',
 'writing': '# 科研写作\n\n## 触发条件\n用户提供段落并请求润色或组织结构时使用。\n\n## 输入\n原文、目标期刊要求和允许改动的范围。\n\n## 步骤\n1. 确认研究目的和论证顺序。\n2. 改善表述，保留事实与引文。\n3. 标出信息缺口。\n\n## 输出\n修改稿及改动说明。\n\n## 约束\n不编造结果、统计值和文献。\n\n## 检查\n核对事实是否保留。\n',
 'literature': '# 文献阅读\n\n## 输入\n用户提供的文献全文或摘录。\n\n## 步骤\n1. 提取研究问题、方法和结果。\n2. 区分作者结论与读者推断。\n3. 汇总限制与可复核依据。\n\n## 输出\n结构化阅读笔记。\n\n## 约束\n缺少全文时明确说明，不虚构检索。\n',
 'tool': '# 工具执行\n\n## 输入\n任务材料和管理员授权的执行配置。\n\n## 步骤\n1. 核对依赖和权限。\n2. 在隔离工具环境执行声明脚本。\n3. 检查真实产物。\n\n## 输出\n真实文件和日志。\n\n## 约束\n管理版不执行脚本；后续需配置隔离环境。\n',
 'visualization': '# 可视化\n\n## 输入\n用户提供的数据、单位与展示目标。\n\n## 步骤\n1. 检查数据完整性。\n2. 选择适合的图表。\n3. 使用已授权绘图工具生成并检查图表。\n\n## 输出\n图表、说明和来源。\n\n## 约束\n不编造数据；未连接工具时只提供方案，不宣称生成文件。\n'
}


def initial(name, description, template='blank'):
    if not isinstance(name,str) or len(name)>64 or not NAME.fullmatch(name):
        raise Fault('INVALID_SKILL_FORMAT','标准名称须用小写字母、数字和单连字符。')
    if not isinstance(description,str) or not 1<=len(description)<=1024:
        raise Fault('INVALID_SKILL_FORMAT','请输入 1～1024 字符的用途描述。')
    return '---\n' + yaml.safe_dump({'name': name, 'description': description}, allow_unicode=True, sort_keys=False) + '---\n\n' + TEMPLATES.get(template, TEMPLATES['blank'])
