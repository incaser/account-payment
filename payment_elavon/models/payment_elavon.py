# -*- coding: utf-8 -*-
from hashlib import sha1
import logging
import urlparse

from openerp import models, fields, api, _
from openerp.addons.payment.models.payment_acquirer import ValidationError
from openerp.tools.float_utils import float_compare
_logger = logging.getLogger(__name__)


class AcquirerElavon(models.Model):
    _inherit = 'payment.acquirer'

    _currency_values = [('EUR', 'Euro'),
                       ('GBP', 'Pound Sterling'),
                       ('USD', 'US Dollar'),
                       ('SEK', 'Swedish Krona'),
                       ('CHF', 'Swiss Franc'),
                       ('HKD', 'Hong Kong Dollar'),
                       ('JPY', 'Japanese Yen')
                       ]

    def _get_elavon_urls(self, environment):
        """ Elavon URLs
        """
        if environment == 'prod':
            return {
                'elavon_form_url':
                'https://hpp.santanderelavontpvvirtual.es/pay',
            }
        else:
            return {
                'elavon_form_url':
                'https://hpp.prueba.santanderelavontpvvirtual.es/pay',
            }

    @api.model
    def _get_providers(self):
        providers = super(AcquirerElavon, self)._get_providers()
        providers.append(['elavon', 'Elavon'])
        return providers

    elavon_merchant_id = fields.Char(
        string='Merchant ID', required_if_provider='elavon', size=50,
        help='Supplied by your payment provider – note this is not the '
             'merchant number supplied by your bank.')
    elavon_account = fields.Char(
        string='Account', size=30,
        help='The sub-account to use for this transaction. If not present, '
             'the default sub-account, ‘internet’, will be used.')
    elavon_currency = fields.Selection(
        _currency_values, string='Currency', required_if_provider='elavon',
        size=3, default='EUR')
    elavon_auto_settle_flag = fields.Boolean(
        string='Auto Settle', default=True,
        help='Used to signify whether or not you wish the transaction to be '
             'captured in the next batch or not. If set to “1” and assuming '
             'the transaction is authorised then it will automatically be '
             'settled in the next batch. If set to “0” then the merchant '
             'must use the realcontrol application to manually settle the '
             'transaction. This option can be used if a merchant wishes to '
             'delay the payment until after the goods have been shipped.'
             'Transactions can be settled for up to 115% of the original '
             'amount. ')
    elavon_return_tss = fields.Boolean(
        string='Return TSS',
        help='Used to signify whether or not you want a Transaction '
             'Suitability Score for this transaction. Can be “0” for no '
             'and “1” for yes. To maximise the usefulness of the realscore '
             'you should also supply the next 6 fields. See below for more '
             'on realscore.')
    elavon_secret_key = fields.Char(
        string='Secret Key', required_if_provider='elavon')

    def _elavon_generate_digital_sign(self, acquirer, inout, values):
        """ Generate the shasign for incoming or outgoing communications.
        :param browse acquirer: the payment.acquirer browse record. It should
                                have a shakey in shaky out
        :param string inout: 'in' (encoding) or 'out' (decoding).
        :param dict values: transaction values

        :return string: shasign
        """
        assert acquirer.provider == 'elavon'

        def get_value(key):
            if values.get(key):
                return values[key]
            return ''

        if inout == 'out':
            keys = ['TIMESTAMP',
                    'MERCHANT_ID',
                    'ORDER_ID',
                    'RESULT',
                    'MESSAGE',
                    'PASREF',
                    'AUTHCODE']
        else:
            keys = ['TIMESTAMP',
                    'MERCHANT_ID',
                    'ORDER_ID',
                    'AMOUNT',
                    'CURRENCY']

        sign = '.'.join('%s' % (get_value(k)) for k in keys)
        # Add the pre-shared secret key at the end of the signature
        if isinstance(sign, str):
            sign = urlparse.parse_qsl(sign)
        shasign = sha1(sign).hexdigest().lower()
        sign = shasign + acquirer.elavon_secret_key
        if isinstance(sign, str):
            sign = urlparse.parse_qsl(sign)
        shasign = sha1(sign).hexdigest().lower()
        return shasign

    @api.model
    def elavon_form_generate_values(self, id, partner_values, tx_values):
        acquirer = self.browse(id)
        sale_order = self.env['sale.order'].search(
            [('name', '=', tx_values['reference'])])
        commercial_partner_id = sale_order.partner_id.commercial_partner_id
        now = fields.Datetime.context_timestamp(self, fields.datetime.now())
        product_description = self._product_description(sale_order)
        elavon_tx_values = dict(tx_values)
        elavon_tx_values.update({
            'MERCHANT_ID': acquirer.elavon_merchant_id,
            'ACCOUNT': acquirer.elavon_account,
            'ORDER_ID': (
                tx_values['reference'] and tx_values['reference'][:40] or
                False),
            'AMOUNT': int(tx_values['amount'] * 100),
            'CURRENCY': acquirer.elavon_currency,
            'TIMESTAMP': now.strftime('%Y%m%d%H%M%S'),
            'AUTO_SETTLE_FLAG':
                acquirer.elavon_auto_settle_flag and '1' or '0',
            'COMMENT1': product_description[:254],
            'COMMENT2': product_description[255:510],
            'RETURN_TSS': acquirer.elavon_return_tss and '1' or '0',
            'SHIPPING_CODE': partner_values['zip'],
            'SHIPPING_CO': partner_values['country'].name, # TODO country name or code
            'BILLING_CODE': commercial_partner_id.zip,
            'BILLING_CO': commercial_partner_id.country_id.name, # TODO country name or code
            'CUST_NUM': commercial_partner_id.ref,
            'VAR_REF': sale_order.client_order_ref,
        })
        elavon_tx_values['SHA1HASH'] = self._elavon_generate_digital_sign(
            acquirer, 'in', elavon_tx_values)
        return partner_values, elavon_tx_values

    @api.multi
    def elavon_get_form_action_url(self):
        return self._get_elavon_urls(self.environment)['elavon_form_url']

    def _product_description(self, sale_order):
        return '|'.join(x.name for x in sale_order.order_line)


class TxElavon(models.Model):
    _inherit = 'payment.transaction'

    elavon_txnid = fields.Char('Transaction ID')

    # --------------------------------------------------
    # FORM RELATED METHODS
    # --------------------------------------------------

    @api.model
    def _elavon_form_get_tx_from_data(self, data):
        """ Given a data dict coming from Elavon, verify it and
        find the related transaction record. """
        reference = data.get('ORDER_ID', '')
        shasign = data.get('SHA1HASH')
        if not reference:
            error_msg = 'Elavon: received data with missing reference (%s)'\
                        % (reference)
            _logger.error(error_msg)
            raise ValidationError(error_msg)

        tx = self.search([('reference', '=', reference)])
        if not tx or len(tx) > 1:
            error_msg = 'Elavon: received data for reference %s' % (reference)
            if not tx:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.error(error_msg)
            raise ValidationError(error_msg)

        # verify shasign
        acquirer = self.env['payment.acquirer']
        shasign_check = acquirer._elavon_generate_digital_sign(
            tx.acquirer_id, 'out', data)
        if shasign_check.lower() != shasign.lower():
            error_msg = 'Elavon: invalid shasign, received %s, computed %s,' \
                ' for data %s' % (shasign, shasign_check, data)
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        return tx

    @api.model
    def _elavon_form_get_invalid_parameters(self, tx, data):
        invalid_parameters = []

        if (tx.acquirer_reference and
                data.get('ORDER_ID')) != tx.acquirer_reference:
            invalid_parameters.append(
                ('Transaction Id', data.get('ORDER_ID'),
                 tx.acquirer_reference))
        # check what is buyed
        if (float_compare(float(data.get('AMOUNT', '0.0')) / 100,
                          tx.amount, 2) != 0):
            invalid_parameters.append(('Amount', data.get('AMOUNT'),
                                       '%.2f' % tx.amount))
        return invalid_parameters

    @api.model
    def _elavon_form_validate(self, tx, data):
        status_code = int(data.get('RESULT', '29999'))
        if status_code == 0:
            tx.write({
                'state': 'done',
                'elavon_txnid': data.get('PASREF'),
                'state_message': _('Ok: %s') % data.get('MESSAGE'),
            })
            email_act = tx.sale_order_id.action_quotation_send()
            # send the email
            if email_act and email_act.get('context'):
                self.send_mail(email_act['context'])
            return True
        else:
            error =  data.get('MESSAGE')
            _logger.info(error)
            tx.write({
                'state': 'error',
                'elavon_txnid': data.get('PASREF'),
                'state_message': error,
            })
            return False

    def send_mail(self, email_ctx):
        composer_values = {}
        template = self.env.ref('sale.email_template_edi_sale', False)
        if not template:
            return True
        email_ctx['default_template_id'] = template.id
        composer_id = self.env['mail.compose.message'].with_context(
            email_ctx).create(composer_values)
        composer_id.with_context(email_ctx).send_mail()
