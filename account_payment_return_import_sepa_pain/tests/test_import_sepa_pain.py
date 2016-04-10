# -*- coding: utf-8 -*-
# © 2016 Carlos Dauden <carlos.dauden@tecnativa.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from openerp.addons.account_payment_return_import.tests import (
    TestPaymentReturnFile)

class TestImport(TestPaymentReturnFile):
    """Run test to import payment return import."""

    def test_payment_return_import(self):
        """Test correct creation of single payment return."""
        transactions = [
            {
                'returned_amount': 100.00,
                'reference': 'E2EID1',
            },
        ]
        self._test_return_import(
            'account_payment_return_import_sepa_pain', 'test-sepa-unpaid.xml',
            'MSGID12345678912',
            local_account='NL77ABNA0574908765',
            date='2016-10-08', transactions=transactions
        )

    def test_zip_import(self):
        """Test import of multiple statements from zip file."""
        self._test_return_import(
            'account_payment_return_import_sepa_pain', 'test-sepa-unpaid.zip',
            'MSGID12345678912',
            local_account='NL77ABNA0574908765',
            date='2016-10-08'
        )
