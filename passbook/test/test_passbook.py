# -*- coding: utf-8 -*-
from __future__ import absolute_import

import json
import os
import tempfile
import pytest

from passbook.models import Barcode, BarcodeFormat, Pass, StoreCard
from passbook.smime_signature import smime_verify

base_path = os.path.realpath('.')

wwdr_certificate = os.path.join(base_path, 'passbook/test/certificates/wwdr_certificate.pem')
certificate = os.path.join(base_path, 'passbook/test/certificates/certificate.pem')
key = os.path.join(base_path, 'passbook/test/certificates/key.pem')
password_file = os.path.join(base_path, 'passbook/test/certificates/password.txt')


def _certificates_mising():
    return not os.path.isfile(wwdr_certificate) or not os.path.isfile(certificate) or not os.path.isfile(key)


def create_shell_pass(barcodeFormat=BarcodeFormat.CODE128):
    cardInfo = StoreCard()
    cardInfo.addPrimaryField('name', 'Jähn Doe', 'Name')
    stdBarcode = Barcode('test barcode', barcodeFormat, 'alternate text')
    passfile = Pass(cardInfo, organizationName='Org Name', passTypeIdentifier='Pass Type ID', teamIdentifier='Team Identifier')
    passfile.barcode = stdBarcode
    passfile.serialNumber = '1234567'
    passfile.description = 'A Sample Pass'
    return passfile


def test_basic_pass():
    passfile = create_shell_pass()
    assert passfile.formatVersion == 1
    assert passfile.barcode.format == BarcodeFormat.CODE128
    assert len(passfile._files) == 0

    passfile_json = passfile.json_dict()
    assert passfile_json is not None
    assert passfile_json['suppressStripShine'] == False
    assert passfile_json['formatVersion'] == 1
    assert passfile_json['passTypeIdentifier'] == 'Pass Type ID'
    assert passfile_json['serialNumber'] == '1234567'
    assert passfile_json['teamIdentifier'] == 'Team Identifier'
    assert passfile_json['organizationName'] == 'Org Name'
    assert passfile_json['description'] == 'A Sample Pass'


def test_manifest_creation():
    passfile = create_shell_pass()
    manifest_json = passfile._createManifest(passfile._createPassJson())
    manifest = json.loads(manifest_json)
    assert 'pass.json' in manifest


def test_header_fields():
    passfile = create_shell_pass()
    passfile.passInformation.addHeaderField('header', 'VIP Store Card', 'Famous Inc.')
    pass_json = passfile.json_dict()
    assert pass_json['storeCard']['headerFields'][0]['key'] == 'header'
    assert pass_json['storeCard']['headerFields'][0]['value'] == 'VIP Store Card'
    assert pass_json['storeCard']['headerFields'][0]['label'] == 'Famous Inc.'


def test_secondary_fields():
    passfile = create_shell_pass()
    passfile.passInformation.addSecondaryField('secondary', 'VIP Store Card', 'Famous Inc.')
    pass_json = passfile.json_dict()
    assert pass_json['storeCard']['secondaryFields'][0]['key'] == 'secondary'
    assert pass_json['storeCard']['secondaryFields'][0]['value'] == 'VIP Store Card'
    assert pass_json['storeCard']['secondaryFields'][0]['label'] == 'Famous Inc.'


def test_back_fields():
    passfile = create_shell_pass()
    passfile.passInformation.addBackField('back1', 'VIP Store Card', 'Famous Inc.')
    pass_json = passfile.json_dict()
    assert pass_json['storeCard']['backFields'][0]['key'] == 'back1'
    assert pass_json['storeCard']['backFields'][0]['value'] == 'VIP Store Card'
    assert pass_json['storeCard']['backFields'][0]['label'] == 'Famous Inc.'


def test_auxiliary_fields():
    passfile = create_shell_pass()
    passfile.passInformation.addAuxiliaryField('aux1', 'VIP Store Card', 'Famous Inc.')
    pass_json = passfile.json_dict()
    assert pass_json['storeCard']['auxiliaryFields'][0]['key'] == 'aux1'
    assert pass_json['storeCard']['auxiliaryFields'][0]['value'] == 'VIP Store Card'
    assert pass_json['storeCard']['auxiliaryFields'][0]['label'] == 'Famous Inc.'


def test_code128_pass():
    """
    This test is to create a pass with a new code128 format,
    freezes it to json, then reparses it and validates it defaults
    the legacy barcode correctly
    """
    passfile = create_shell_pass()
    jsonData = passfile._createPassJson()
    thawedJson = json.loads(jsonData)
    assert thawedJson['barcode']['format'] == BarcodeFormat.PDF417
    assert thawedJson['barcodes'][0]['format'] == BarcodeFormat.CODE128


def test_pdf_417_pass():
    """
    This test is to create a pass with a barcode that is valid
    in both past and present versions of IOS
    """
    passfile = create_shell_pass(BarcodeFormat.PDF417)
    jsonData = passfile._createPassJson()
    thawedJson = json.loads(jsonData)
    assert thawedJson['barcode']['format'] == BarcodeFormat.PDF417
    assert thawedJson['barcodes'][0]['format'] == BarcodeFormat.PDF417


def test_files():
    dummy_image = os.path.join(base_path, 'passbook/test/static/white_square.png')

    passfile = create_shell_pass()
    passfile.addFile('icon.png', open(dummy_image, 'rb'))
    assert len(passfile._files) == 1
    assert 'icon.png' in passfile._files

    manifest_json = passfile._createManifest(passfile._createPassJson())
    manifest = json.loads(manifest_json)
    assert '170eed23019542b0a2890a0bf753effea0db181a' == manifest['icon.png']

    passfile.addFile('logo.png', open(dummy_image, 'rb'))
    assert len(passfile._files) == 2
    assert 'logo.png' in passfile._files

    manifest_json = passfile._createManifest(passfile._createPassJson())
    manifest = json.loads(manifest_json)
    assert '170eed23019542b0a2890a0bf753effea0db181a' == manifest['logo.png']


@pytest.mark.skipif(_certificates_mising(), reason='Certificates missing')
def test_signing():
    """
    This test can only run locally if you provide your personal Apple Wallet
    certificates, private key and password. It would not be wise to add
    them to git. Store them in the files indicated below, they are ignored
    by git.
    """
    manifest_file = os.path.join(base_path, 'passbook/test/temp/wmanifest.json')
    signature_file = os.path.join(base_path, 'passbook/test/temp/signature.der')

    try:
        with open(password_file, 'r') as file_:
            password = file_.read().strip()
    except IOError:
        password = ''

    passfile = create_shell_pass()
    manifest_json = passfile._createManifest(passfile._createPassJson())

    with open(manifest_file, 'w') as file_:
        file_.write(manifest_json)

    signature = passfile._createSignature(
        manifest=manifest_json,
        certificate=certificate,
        key=key,
        wwdr_certificate=wwdr_certificate,
        password=password,
    )

    with open(signature_file, 'wb') as file_:
        file_.write(signature)

    assert smime_verify(
        signer_cert_path=wwdr_certificate,
        content_path=manifest_file,
        signature_path=signature_file,
        signature_format='DER',
        noverify=True,
    ) is True

    # If the content of the manifest is wrong, the verification of the
    # signature must fail.
    tampered_manifest = '{"pass.json": "foobar"}'

    with open(manifest_file, 'w') as file_:
        file_.write(tampered_manifest)

    assert smime_verify(
        signer_cert_path=wwdr_certificate,
        content_path=manifest_file,
        signature_path=signature_file,
        signature_format='DER',
        noverify=True,
    ) is False


@pytest.mark.skipif(_certificates_mising(), reason='Certificates missing')
def test_passbook_creation():
    """
    This test can only run locally if you provide your personal Apple Wallet
    certificates, private key and password. It would not be wise to add
    them to git. Store them in the files indicated below, they are ignored
    by git.
    """
    try:
        with open(password_file, 'rb') as file_:
            password = file_.read().strip().decode('utf-8')
    except IOError:
        password = ''

    passfile = create_shell_pass()
    dummy_image = os.path.join(base_path, 'passbook/test/static/white_square.png')
    passfile.addFile('icon.png', open(dummy_image, 'rb'))

    tf = tempfile.TemporaryFile()
    passfile.create(certificate, key, wwdr_certificate, password, tf)
