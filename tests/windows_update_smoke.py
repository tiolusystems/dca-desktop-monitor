"""Real packaged updater, backup, fresh GUI handshake and native Desktop shortcut.

Only an isolated synthetic wallet and GitHub-hosted runner Desktop are used.
The old-version argument models the requesting version; both helper and candidate
are the newly built binary. This is not a claim that the 1.0.0 binary can update.
"""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app_lifecycle import APP_VERSION
from backend.backend import DataManager
from backend.update_install import preparar_instalacao, sha256


def main():
    assert sys.platform=='win32'
    kernel=ctypes.windll.kernel32
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    archive=ROOT/f'DCA-Monitor-v{APP_VERSION}-Windows-x64.zip'
    source=ROOT/'dist/DCA-Monitor/DCA-Monitor.exe'
    with tempfile.TemporaryDirectory(prefix='dca-update-real-') as temp:
        root=Path(temp)
        local=root/'local';local.mkdir()
        env={**os.environ,'LOCALAPPDATA':str(local)}
        dm=DataManager(data_dir=root/'wallet',auto_import_legacy=False)
        assert dm.salvar_operacao(['2026-01-01 12:00:00','USDT','compra',
                                  '10.123456789123456789','5','10.123456789123456789','5'])
        bank_before=dm.arquivo_db.read_bytes()
        name=archive.name
        info=dict(download_disponivel=True,versao_publicada=APP_VERSION,pacote=dict(
            nome=name,url=f'https://github.com/tiolusystems/dca-desktop-monitor/releases/download/v{APP_VERSION}/{name}',
            tamanho=archive.stat().st_size,sha256=sha256(archive)))
        plan=preparar_instalacao(info,archive,dm.arquivo_db,
             version_atual='1.0.0',raiz=local/'Programs/DCA-Monitor/versions',origem=source)
        action=Path(plan['acao'])
        process=subprocess.Popen([str(source),'--maintenance-update',str(action)],env=env,cwd=source.parent)
        shortcut=None;candidate=None
        try:
            assert process.wait(timeout=150)==0,action.read_text()
            receipt=json.loads(action.read_text())
            assert receipt['state']=='installed',receipt
            assert Path(receipt['backup']['pacote']).is_file()
            assert dm.arquivo_db.read_bytes()==bank_before
            shortcut=Path(receipt['shortcut']['atalho'])
            assert shortcut.is_file()
            # Inspect the real .lnk via the same native COM API Explorer uses.
            quote=str(shortcut).replace("'","''")
            inspection=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',
                "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('"+quote+
                "'); @{target=$s.TargetPath;icon=$s.IconLocation;arguments=$s.Arguments} | ConvertTo-Json -Compress"],
                capture_output=True,text=True,check=True,timeout=20)
            link=json.loads(inspection.stdout)
            expected=str(Path(plan['destino'])/'DCA-Monitor.exe')
            assert link['target']==expected,link
            assert link['icon'].split(',')[0]==expected,link
            assert not link['arguments'],link
            candidate=ctypes.windll.kernel32.OpenProcess(0x100000|0x1000,False,receipt['pid'])
            assert candidate
            # Close the real new GUI normally; never terminate it as success evidence.
            callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
            def close(hwnd,_):
                pid=wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                if pid.value==receipt['pid'] and ctypes.windll.user32.IsWindowVisible(hwnd):
                    ctypes.windll.user32.PostMessageW(hwnd,0x0010,0,0)
                return True
            ctypes.windll.user32.EnumWindows(callback_type(close),0)
            assert ctypes.windll.kernel32.WaitForSingleObject(candidate,30000)==0
            assert dm.arquivo_db.read_bytes()==bank_before
            print('WINDOWS_REAL_UPDATE_BACKUP_GUI_RECEIPT_SHORTCUT=PASS')
            print('WINDOWS_REAL_UPDATE_PRECISE_SQLITE_AND_NORMAL_CLOSE=PASS')
        finally:
            if candidate:ctypes.windll.kernel32.CloseHandle(candidate)
            if process.poll() is None:
                process.kill();process.wait()  # failure cleanup only
            if shortcut and shortcut.is_file():shortcut.unlink()


if __name__=='__main__':main()
