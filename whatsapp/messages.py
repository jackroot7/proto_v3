"""
WhatsApp message composers for Proto v3 - Twilio.

Twilio sends free-form text, so we compose the full message here.
Each function returns (message_text, media_url_or_none).
"""

from django.utils import timezone


def daily_report_message(day_session, pdf_url: str = None) -> tuple:
    """
    Returns (message, media) for a daily closing report.
    pdf_url: publicly accessible URL to the PDF (Twilio fetches it for attachment).
    """
    lines = [
        f"📊 *{day_session.shop.name} - Daily Report*",
        f"📅 {day_session.date.strftime('%A, %d %B %Y')}",
        f"",
        f"💰 Revenue: TSh {float(day_session.total_sales or 0):,.0f}",
        f"🧾 Transactions: {day_session.total_transactions or 0}",
        f"",
        f"💵 Cash: TSh {float(day_session.total_cash or 0):,.0f}",
        f"📱 M-Pesa: TSh {float(day_session.total_mpesa or 0):,.0f}",
        f"🤝 Credit: TSh {float(day_session.total_credit or 0):,.0f}",
        f"",
        f"📈 Gross Profit: TSh {float(getattr(day_session, 'gross_profit', 0) or 0):,.0f}",
        f"",
        f"_Sent by Proto v3 at {timezone.now().strftime('%H:%M')}_",
    ]
    return '\n'.join(lines), pdf_url


def credit_reminder_message(customer) -> tuple:
    """Returns (message, None) for a credit/debt reminder."""
    lines = [
        f"👋 Hello *{customer.name}*,",
        f"",
        f"This is a friendly reminder that you have an outstanding balance of:",
        f"",
        f"💳 *TSh {float(customer.credit_balance):,.0f}*",
        f"",
        f"Please visit us at your earliest convenience to settle this balance.",
        f"Thank you for your continued support! 🙏",
    ]
    return '\n'.join(lines), None


def receipt_message(sale) -> tuple:
    """Returns (message, None) for a sale receipt sent to customer."""
    lines = [
        f"🧾 *Receipt - {sale.sale_number}*",
        f"📍 {sale.shop.name}",
        f"📅 {sale.created_at.strftime('%d %b %Y %H:%M')}",
        f"",
    ]
    for item in sale.items.select_related('product').all():
        lines.append(f"• {item.product.name} ×{item.quantity} - TSh {float(item.line_total):,.0f}")
    lines += [
        f"",
        f"💰 *Total: TSh {float(sale.total):,.0f}*",
        f"💳 {sale.get_payment_method_display()}",
    ]
    if sale.change_given and sale.change_given > 0:
        lines.append(f"💵 Change: TSh {float(sale.change_given):,.0f}")
    lines.append(f"\n_Thank you for shopping with us!_")
    return '\n'.join(lines), None


def low_stock_message(shop_name: str, items) -> tuple:
    """Returns (message, None) for a low stock alert."""
    lines = [
        f"⚠️ *Low Stock Alert - {shop_name}*",
        f"",
    ]
    for item in items:
        uom = item.product.uom.short_name if item.product.uom else 'units'
        lines.append(f"• {item.product.name}: *{item.quantity} {uom}* remaining")
    lines.append(f"\n_Proto v3 Stock Manager_")
    return '\n'.join(lines), None


def purchase_order_message(order) -> tuple:
    """Returns (message, None) for a purchase order notification to supplier."""
    lines = [
        f"📦 *Purchase Order - {order.order_number}*",
        f"From: {order.shop.name}",
        f"Date: {order.order_date.strftime('%d %b %Y')}",
        f"",
        f"*Items:*",
    ]
    for item in order.items.select_related('product').all():
        uom = item.product.uom.short_name if item.product.uom else 'units'
        lines.append(f"• {item.product.name}: {item.quantity_ordered} {uom} @ TSh {float(item.unit_cost):,.0f}")
    lines += [
        f"",
        f"💰 *Total: TSh {float(order.total):,.0f}*",
        f"📅 Expected: {order.expected_date or 'TBD'}",
        f"_Proto v3 Purchasing_",
    ]
    return '\n'.join(lines), None