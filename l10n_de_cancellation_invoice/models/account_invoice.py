from functools import partial

from odoo import _, api, fields, models
from odoo.tools import date
from odoo.tools.misc import formatLang


class AccountInvoiceCannelation(models.Model):
    _inherit = "account.invoice"

    origin_invoice_id = fields.Many2one(
        string="Origin Invoice",
        comodel_name="account.invoice",
        compute="_compute_origin_invoice_id",
    )

    credit_type = fields.Selection(
        string="Credit Type",
        selection=[
            ("credit", "Credit"),
            ("correction_invoice", "Correction Invoice"),
            ("cancellation_invoice", "Cancellation Invoice"),
        ],
        compute="_compute_credit_type",
    )

    @api.multi
    def _compute_origin_invoice_id(self):
        """
        Computes the origin invoice, from where the credit note was issued.

        This is achieved by looking up with which invoices the credit note was
        reconciled.
        """
        for inv in self.filtered(
            lambda inv: inv.type in ("out_refund", "in_refund")
        ):
            payment_vals = inv._get_payments_vals()

            inv.origin_invoice_id = self.browse(
                [x.get("invoice_id", 0) for x in payment_vals]
            )

    @api.multi
    def _compute_credit_type(self):
        """
        Computes the credit type of the credit note.

        We distinguish three different types of credit notes:

        Credit Note:
            If there is no invoice reconciled with the credit note, it's
            considered as a usual credit, not crediting another invoice.

        Correction Invoice:
            If the credit note is partially reconciling another origin invoice,
            it's considered as a correction invoice.

        Cancellation Invoice:
            If the credit note fully reconciles the origin invoice, it's
            considered as a cancellation invoice.

        """

        for inv in self.filtered(
            lambda inv: inv.type in ("out_refund", "in_refund")
        ):

            if not inv.origin_invoice_id:
                inv.credit_type = "credit"

            else:
                fully_reconciled = inv.amount_total == sum(
                    x.amount_total for x in inv.origin_invoice_id
                )

                inv.credit_type = (
                    "cancellation_invoice"
                    if fully_reconciled
                    else "correction_invoice"
                )

    def _get_singed_value(self, value):
        """
        Returns the given value signed to be compliant with the
        German Cancellation Invoice standards

        Returns:
            The given value with the correct sign
        """

        sign = self.type in ["in_refund", "out_refund"] and -1 or 1

        return value * sign

    def _amount_by_group(self):
        """
        Signs the tax values of the invoice.

        The tax values are computed and stored in a binary field by
        this method in the core account module. We overwrite it, to
        also sign the tax values.

        Returns:
            The computed tax values, but signed
        """

        for invoice in self:

            super(AccountInvoiceCannelation, invoice)._amount_by_group()

            if not invoice.type in ["in_refund", "out_refund"]:
                continue

            sign = -1

            currency = invoice.currency_id or invoice.company_id.currency_id

            fmt = partial(
                formatLang,
                invoice.with_context(lang=invoice.partner_id.lang).env,
                currency_obj=currency,
            )

            singed_taxes = list()

            for tax in invoice.amount_by_group:
                tax_list = list(tax)
                tax_list[1] = tax_list[1] * sign
                tax_list[2] = tax_list[2] * sign
                tax_list[3] = fmt(tax_list[1])
                tax_list[4] = fmt(tax_list[2])

                singed_taxes.append(tuple(tax_list))

            invoice.amount_by_group = singed_taxes
