"""NC-05: Start Menu links are updated only if previously owned/present."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest

from config.install import APP_NAME, install_menu_iniciar_windows
from backend.backend import DataManager
from backend.update_install import executar_instalacao, preparar_instalacao, sha256

import hashlib
import zipfile
import sys


class MenuExistingShortcutTest(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.menu=self.root/"menu"
        self.menu.mkdir()

    def test_absent_menu_shortcut_not_created(self):
        with patch("config.install.install_windows") as install:
            result=install_menu_iniciar_windows(
                menu_iniciar=self.menu, executavel=self.root/"new.exe",
                somente_se_existente=True)
        self.assertTrue(result["ignorado"])
        self.assertFalse(result["criado"])
        install.assert_not_called()
        self.assertFalse(list(self.menu.iterdir()))

    def test_existing_owned_link_is_updated_after_verified_policy(self):
        old=self.menu/(APP_NAME+".lnk")
        old.write_bytes(b"OLD USER SHORTCUT")
        new=self.root/"new.exe"
        with patch("config.install.install_windows",
                   return_value={"criado":True,"proprio":True,
                                 "status":"Atalho criado e verificado."}) as install:
            result=install_menu_iniciar_windows(
                menu_iniciar=self.menu, executavel=new,
                anterior=self.root/"old.exe",somente_se_existente=True)
        install.assert_called_once_with(
            executavel=new,anterior=self.root/"old.exe",desktop=self.menu)
        self.assertTrue(result["proprio"])

    def test_existing_foreign_link_is_not_overwritten(self):
        link=self.menu/(APP_NAME+".lnk")
        link.write_bytes(b"THIRD PARTY")
        with patch("config.install.install_windows",
                   return_value={"criado":False,"proprio":False,
                                 "status":"Atalho existente de outra instalação preservado."}):
            result=install_menu_iniciar_windows(
                menu_iniciar=self.menu,somente_se_existente=True)
        self.assertFalse(result["proprio"])
        self.assertEqual(link.read_bytes(),b"THIRD PARTY")


class AcknowledgedUpdateMenuTest(unittest.TestCase):
    def test_two_shortcuts_retarged_only_after_gui_receipt(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            wallet=DataManager(data_dir=root/"wallet",auto_import_legacy=False)
            wallet.salvar_operacao(
                ["2026-01-01 12:00:00","USDT","compra","10","5","10","5"])
            version="1.1.0"
            files={"DCA-Monitor.exe":b"FAKE INERT EXE",
                   "_internal/file.txt":b"content"}
            manifest={
                "format":"DCA-DISTRIBUTION-1","version":version,
                "commit":"a"*40,
                "files":{k:hashlib.sha256(v).hexdigest() for k,v in files.items()},
            }
            archive=root/("DCA-Monitor-v"+version+"-Windows-x64.zip")
            with zipfile.ZipFile(archive,"w") as z:
                for name,raw in files.items():
                    z.writestr("DCA-Monitor/"+name,raw)
                z.writestr("DCA-Monitor/distribution-manifest.json",
                           json.dumps(manifest))
            info={"download_disponivel":True,"versao_publicada":version,
                  "pacote":{
                      "nome":archive.name,
                      "url":("https://github.com/tiolusystems/dca-desktop-monitor/"
                             "releases/download/v"+version+"/"+archive.name),
                      "sha256":sha256(archive),"tamanho":archive.stat().st_size,
                  }}
            target_root=(root/"versions").resolve()
            staged=preparar_instalacao(
                info,archive,wallet.arquivo_db,
                raiz=target_root,origem=Path(sys.executable).resolve())
            action=Path(staged["acao"])
            candidate=Path(staged["destino"])/"DCA-Monitor.exe"
            source=Path(sys.executable).resolve()
            def launch(args,**kwargs):
                state=json.loads(action.read_text())
                assert state["state"]=="starting"
                action.with_suffix(".ready.json").write_text(
                    json.dumps({"token":state["token"],
                                "version":version,
                                "executable":str(candidate),
                                "pid":112233}))
                proc=Mock(pid=112233)
                proc.poll.return_value=None
                return proc
            with patch("backend.update_install.raiz_instalacoes",return_value=target_root), \
                 patch("backend.update_install.subprocess.Popen",side_effect=launch), \
                 patch("backend.update_install.TravaInstancia"), \
                 patch("backend.update_install.sys.platform","win32"), \
                 patch("config.install.install_windows",
                       return_value={"criado":True,"proprio":True}) as desktop, \
                 patch("config.install.install_menu_iniciar_windows",
                       return_value={"criado":True,"proprio":True}) as menu:
                final=executar_instalacao(action)
            self.assertEqual(final["state"],"installed")
            desktop.assert_called_once_with(
                executavel=candidate, anterior=source)
            menu.assert_called_once_with(
                executavel=candidate,anterior=source,
                somente_se_existente=True)
            self.assertTrue(final["menu_iniciar"]["proprio"])


if __name__=="__main__":
    unittest.main()
