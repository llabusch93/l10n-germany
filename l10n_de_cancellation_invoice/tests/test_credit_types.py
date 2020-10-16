import json

from odoo.tests import SavepointCase, tagged, HttpCase


# @tagged("post_install", "l10n_de")
class TestCancellationInvoice(SavepointCase):
    """
    Test class for several checks on the cancellation invoice type
    mechanism.
    """

    @classmethod
    def setUpClass(cls):
        """
        Setting up the invoice for the test cases
        """
        super(TestCancellationInvoice, cls).setUpClass()

        partner_id = cls.env["res.partner"].create({"name": "Test Partner"})

        cls.invoice_id = cls.env["account.invoice"].create(
            {"partner_id": partner_id.id}
        )

        test_product_id = cls.env["product.product"].create(
            {"name": "Test Product", "list_price": 100.0, "costs": 40.0}
        )

        # Get random income account
        account_id = cls.env["account.account"].search(
            [("user_type_id.name", "ilike", "income")], limit=1
        )

        inv_line_1 = cls.env["account.invoice.line"].create(
            {
                "name": "Test Line 1",
                "account_id": account_id.id,
                "product_id": test_product_id.id,
                "quantity": 5,
                "price_unit": 100,
            }
        )

        inv_line_2 = cls.env["account.invoice.line"].create(
            {
                "name": "Test Line 2",
                "account_id": account_id.id,
                "product_id": test_product_id.id,
                "quantity": 3,
                "price_unit": 50,
            }
        )

        cls.invoice_id.invoice_line_ids |= inv_line_1 + inv_line_2

        cls.invoice_id.action_invoice_open()

        cls.refund_wizard = (
            cls.env["account.invoice.refund"]
            .with_context(active_ids=cls.invoice_id.ids)
            .create(
                {
                    "description": "Test Refund",
                    "date_invoice": cls.invoice_id.date_invoice,
                }
            )
        )

    def test_cancellation_invoice(self):
        """
        Test if the correct credit_type is computed, when the invoice amount
        is completely credited.
        """

        # This refund mode will credit the whole invoice and reconcile
        # the amount
        self.refund_wizard.filter_refund = "cancel"

        view_action = self.refund_wizard.invoice_refund()

        refund_invoice_id = self.env["account.invoice"].browse(
            view_action["domain"][1][2]
        )

        self.assertEqual(
            refund_invoice_id.credit_type, "cancellation_invoice"
        )

    def test_correction_invoice(self):
        """
        Test if the credit_type is 'correction_invoice' for partial
        credit notes
        """
        self.refund_wizard.filter_refund = "refund"

        view_action = self.refund_wizard.invoice_refund()

        refund_invoice_id = self.env["account.invoice"].browse(
            view_action["domain"][1][2]
        )

        # We lower the quantity of the first credit note invoice line, so the
        # invoice total lowers as well, what results in a partial refund
        refund_invoice_id.invoice_line_ids[0].quantity = 1

        refund_invoice_id.action_invoice_open()

        # Reconcile with the origin invoice thru the payments widget
        outstanding_widget = json.loads(
            refund_invoice_id.outstanding_credits_debits_widget
        )
        credit_aml_id = outstanding_widget["content"][0]["id"]
        refund_invoice_id.assign_outstanding_credit(credit_aml_id)

        self.assertEqual(refund_invoice_id.credit_type, "correction_invoice")

    def test_credit_note(self):
        """
        Test if the credit_type is 'credit' for usual credit notes
        """

        refund_invoice_id = self.invoice_id.copy()

        refund_invoice_id.type = "out_refund"

        refund_invoice_id.action_invoice_open()

        self.assertEqual(refund_invoice_id.credit_type, "credit")
