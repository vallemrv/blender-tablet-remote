"""Creación de carpetas desde el explorador, sin modificar la escena."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import file
from blender_tablet_remote.errors import BadPayload, CommandError

class FolderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.root=Path(self.temp.name)
        self.default=patch.object(file,'_load_default_folder',return_value=str(self.root));self.default.start()
    def tearDown(self):
        self.default.stop();self.temp.cleanup()
    def test_create_unicode_folder_and_enter_without_changing_default(self):
        result=file.make_directory(dict(folder='@default',name='  Piezas válidas  '))
        self.assertEqual(result['path'],str(self.root/'Piezas válidas'))
        self.assertEqual(result['parent'],str(self.root));self.assertEqual(result['entries'],[])
        self.assertEqual(result['default_folder'],str(self.root))
    def test_existing_file_folder_or_symlink_is_never_overwritten(self):
        (self.root/'carpeta').mkdir();(self.root/'fichero').write_text('conservar')
        (self.root/'enlace').symlink_to(self.root/'carpeta',target_is_directory=True)
        for name in ('carpeta','fichero','enlace'):
            with self.assertRaises(CommandError) as error:file.make_directory(dict(folder=str(self.root),name=name))
            self.assertEqual(error.exception.code,'already_exists')
        self.assertEqual((self.root/'fichero').read_text(),'conservar')
    def test_rejects_paths_and_does_not_create_intermediate_folders(self):
        for name in ('','  ','.','..','../outside','a/b','a\\b','C:drive','nul\0name',None):
            with self.subTest(name=name):
                with self.assertRaises(BadPayload):file.make_directory(dict(folder=str(self.root),name=name))
        self.assertEqual(list(self.root.iterdir()),[])
    def test_missing_parent_and_permissions_are_recoverable_errors(self):
        with self.assertRaises(CommandError) as error:file.make_directory(dict(folder=str(self.root/'missing'),name='child'))
        self.assertEqual(error.exception.code,'not_found')
        with patch.object(file.os,'mkdir',side_effect=PermissionError()):
            with self.assertRaises(CommandError) as error:file.make_directory(dict(folder=str(self.root),name='child'))
            self.assertEqual(error.exception.code,'access_denied')

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FolderTests))
    if not result.wasSuccessful():raise SystemExit(1)
