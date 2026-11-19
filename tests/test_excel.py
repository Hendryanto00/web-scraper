import unittest
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from fastapi import HTTPException
from app.main import ExcelRequest, export_excel


class ExcelTests(unittest.TestCase):
    def test_preserves_text_and_produces_valid_xml(self):
        response = export_excel(ExcelRequest(headers=['Nama', 'ID'], rows=[['Ani & <B>', '00123'], ['=1+1\x00', '']]))
        with ZipFile(BytesIO(response.body)) as archive:
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        self.assertEqual([node.text or '' for node in sheet.findall('.//s:t', ns)], ['Nama', 'ID', 'Ani & <B>', '00123', '=1+1', ''])
        self.assertEqual(sheet.findall('.//s:f', ns), [])
        self.assertIn('attachment;', response.headers['content-disposition'])

    def test_rejects_mismatched_columns(self):
        with self.assertRaises(HTTPException):
            export_excel(ExcelRequest(headers=['Nama'], rows=[['Ani', '123']]))
