import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from proto_mind import native_documents as documents
from proto_mind.native_workspace import WorkspaceReader


class DocumentToolsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.reader = WorkspaceReader(str(self.root))

    def test_real_office_roundtrips_and_existing_file_is_preserved(self):
        samples = {'docx':{'title':'Привет','paragraphs':['Actual content']},
                   'xlsx':{'sheets':[{'name':'Budget','rows':[['Item','EUR'],['Design',1200],['=1+1',None]]}]},
                   'pptx':{'slides':[{'title':'Proto-Mind','bullets':['Actual first point','Actual second point']}]}}
        for suffix,spec in samples.items():
            with self.subTest(suffix=suffix):
                name='sample.'+suffix
                result=documents.create(self.reader,name,spec)
                self.assertTrue(result['saved']); self.assertFalse(result['visual_verification'])
                before=(self.root/name).read_bytes()
                preview=documents.inspect(self.reader,name)
                self.assertEqual(preview['sha256'],result['sha256'])
                self.assertTrue(preview['content'])
                with self.assertRaisesRegex(ValueError, 'already exists'): documents.create(self.reader,name,spec)
                self.assertEqual((self.root/name).read_bytes(),before)
        from openpyxl import load_workbook
        book=load_workbook(self.root/'sample.xlsx'); self.assertEqual(book.active['A3'].data_type,'s'); book.close()

    def test_pdf_is_real_and_unicode_is_preserved_in_authoring(self):
        result=documents.create(self.reader,'sample.pdf',{'title':'Привет','paragraphs':['Проверка документа и текста.']})
        self.assertTrue((self.root/'sample.pdf').read_bytes().startswith(b'%PDF-'))
        self.assertGreater(result['bytes'],1000)

    def test_symlinks_and_parent_escape_are_rejected(self):
        (self.root/'alias').symlink_to(self.root,target_is_directory=True)
        for path in ['../outside.docx','alias/escape.docx','.env']:
            with self.assertRaises((ValueError,OSError)): documents.create(self.reader,path,{'paragraphs':['x']})
        self.assertFalse((self.root/'escape.docx').exists())

    def test_xml_entities_are_rejected_before_office_parser(self):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive: archive.writestr('word/document.xml','<!DOCTYPE a [<!ENTITY secret SYSTEM "file:///etc/passwd">]><a>&secret;</a>')
        (self.root/'bad.docx').write_bytes(output.getvalue())
        with self.assertRaisesRegex(ValueError,'entities'): documents.inspect(self.reader,'bad.docx')

    def test_bad_spec_never_publishes_a_file(self):
        with self.assertRaises(ValueError): documents.create(self.reader,'bad.xlsx',{'sheets':[{'name':'x','rows':[[float('nan')]]}]})
        self.assertEqual(list(self.root.iterdir()),[])

    def test_runtime_is_ready_and_explicit(self):
        value=documents.environment()
        self.assertIn('python-docx',value['packages']); self.assertTrue(Path(value['python']).is_file())
        self.assertNotIn('key',value)
