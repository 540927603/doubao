# -*- coding: utf-8 -*-
"""安装文件静默自检(2026-11-25 收敛: 只写日志, 永不弹窗、不触发修复)。

打包期 build_exe.write_files_manifest() 在安装器 payload 根写 files.manifest.json
(相对路径 → 字节数); 客户端启动后由 bridge._kick_integrity_scan() 延迟触发一次
轻量核对 —— 仅比对存在性与大小, 不读文件内容, 结果只落 integrity 日志。
远程排障时一眼看出是哪个文件被安全软件移走/截断。

根级主 exe 不在清单里: 安装器 ssPostInstall 会按品牌给它改名、追加品牌尾部、
替换图标资源, 大小必然与打包期不同(曾因此每次启动误报「文件被修改」)。"""
import json
import os
import sys

_log = None


def log_fn():
    global _log
    if _log is None:
        from . import logcenter
        _log = logcenter.log_fn('integrity')
    return _log


def manifest_path() -> str:
    """清单位置: PyInstaller onedir 下 exe 同级 files.manifest.json。"""
    return os.path.join(os.path.dirname(sys.executable), 'files.manifest.json')


def load_manifest():
    """读清单, 不存在/损坏返回 None(开发模式或清单被删, 不判罚)。"""
    try:
        with open(manifest_path(), 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        files = data.get('files') if isinstance(data, dict) else None
        return files if isinstance(files, dict) and files else None
    except Exception:  # noqa: BLE001 读不到清单 = 不核对, 绝不因自检拖累启动
        return None


def scan():
    """按清单核对安装目录。返回 {skipped(原因, 空串=真核对了), total, broken}。
    broken 项: {path, issue: missing|size|error, expect, got}。"""
    files = load_manifest()
    if not files:
        return {'skipped': 'no_manifest', 'total': 0, 'broken': []}
    root = os.path.dirname(sys.executable)
    broken = []
    for rel, meta in files.items():
        rel = str(rel or '').strip().replace('\\', '/')
        if not rel or rel.startswith('..') or os.path.isabs(rel):
            continue  # 清单异常时不越出安装目录
        p = os.path.join(root, rel)
        try:
            expect = int((meta or {}).get('size') or -1)
            if not os.path.isfile(p):
                broken.append({'path': rel, 'issue': 'missing', 'expect': expect, 'got': 0})
            elif expect >= 0 and os.path.getsize(p) != expect:
                broken.append({'path': rel, 'issue': 'size', 'expect': expect,
                               'got': os.path.getsize(p)})
        except Exception as e:  # noqa: BLE001 单文件异常不中断核对
            broken.append({'path': rel, 'issue': 'error', 'expect': '', 'got': e.__class__.__name__})
    try:
        if broken:
            log_fn()('安装文件自检发现 %d 个异常(共 %d): %s'
                     % (len(broken), len(files),
                        ', '.join('%s(%s)' % (b['path'], b['issue']) for b in broken[:8])),
                     level='error')
        else:
            log_fn()('安装文件自检通过: %d 个文件齐全' % len(files))
    except Exception:  # noqa: BLE001
        pass
    return {'skipped': '', 'total': len(files), 'broken': broken}
