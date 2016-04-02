# -*- coding: utf-8 -*-
# © 2016 Carlos Dauden <carlos.dauden@tecnativa.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp.addons.account_payment_return_import.tests import (
    TestAccountPaymentReturnImport)


class TestImport(TestAccountPaymentReturnImport):
    """Run test to import payment return import."""

    def test_payment_return_import(self):
        """Test correct creation of single payment return."""
        transactions = [
            {
            },
        ]
        self._test_payment_return_import(
        )
