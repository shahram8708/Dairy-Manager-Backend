"""Production seed for the Dairy Manager backend.

Sources: the two product price sheets dated 2026-07-17 and the two handwritten
route sheets dated 2026-07-12. Product names, pack counts and RETAILER-column
values are transcribed from the sheets. The route sheets contain Gujarati
dealer names, but no reliable addresses, dealer phones, credit limits or
balances; therefore those fields are intentionally None/zero. Names are
rendered in English phonetic form where they are proper names. The route sheets
explicitly identify NR Marketing (AM) and Swara Agency (PM), so dealers are
grouped under those existing/default agencies.

Run from this directory: python seed.py [--reset]. Default operation is
additive and idempotent. --reset removes only rows whose natural keys are in
this file (and their price rows); it never removes users, agencies, settings,
or unrelated records. All writes use the application's db/session.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from decimal import Decimal

from app import app
from models import (
    db,
    Agency,
    Dealer,
    Product,
    ProductPrice,
    User,
    BusinessSettings,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("dairy-seed")


AGENCIES = [
    {
        "name": "NR Marketing",
        "shift_label": "AM",
        "contact_person": "Urvish Patel",
        "phone": "9924190055",
    },
    {
        "name": "Swara Agency",
        "shift_label": "PM",
        "contact_person": "Urvish Patel",
        "phone": "9924190055",
    },
]


# Gujarati handwriting is partly obscured. These are the readable shop/name
# renderings; absent financial/contact fields are not guessed.
DEALERS = [
    ("Vraj Dairy", "NR Marketing"),
    ("Umiya Dairy", "NR Marketing"),
    ("Amul Jalsa", "NR Marketing"),
    ("Krupa Dairy", "NR Marketing"),
    ("Mitali", "NR Marketing"),
    ("Ramesh", "NR Marketing"),
    ("Shree Dairy", "NR Marketing"),
    ("Kinna (APO)", "NR Marketing"),
    ("Subhash", "NR Marketing"),
    ("Matu", "NR Marketing"),
    ("Maulik", "NR Marketing"),
    ("Kailashbhai", "NR Marketing"),
    ("Ishwar Patel", "NR Marketing"),
    ("Mahakali", "NR Marketing"),
    ("Shree Krishna", "Swara Agency"),
    ("Uma Medical", "Swara Agency"),
    ("Shiv Market", "Swara Agency"),
    ("Ghanshyam", "Swara Agency"),
    ("Himat-2", "Swara Agency"),
    ("Sivam", "Swara Agency"),
    ("Bhavani", "Swara Agency"),
    ("Shree Dairy", "Swara Agency"),
    ("Mata", "Swara Agency"),
    ("Mahadev", "Swara Agency"),
    ("Shree Vinayak", "Swara Agency"),
    ("Shivam", "Swara Agency"),
    ("Mahalaxmi", "Swara Agency"),
    ("Shree Krishna (Grocery)", "Swara Agency"),
]


# name, pack_size, outer_unit, pieces_per_unit, RETAILER price.
# These values are taken from the RETAILER columns, not the MRP columns.
PRODUCTS = [
    ("BF 24*500", "500 ml", "Crate", 24, "908.3"),
    ("BF 12*1 L", "1 L", "Crate", 12, "908.3"),
    ("BF 2*6 L", "6 L", "Crate", 2, "859.2"),
    ("Gold 24*500", "500 ml", "Crate", 24, "817.8"),
    ("Gold 12*1 L", "1 L", "Crate", 12, "817.2"),
    ("Gold 6*2 L pouch", "2 L", "Crate", 6, "797.4"),
    ("Gold 2*6 L Pouch", "6 L", "Crate", 2, "768.1"),
    ("Shakti 24*500", "500 ml", "Crate", 24, "747.0"),
    ("T-Special 12*1 L", "1 L", "Crate", 12, "769.8"),
    ("CM 24*500 ml", "500 ml", "Crate", 24, "697.2"),
    ("Desi CM 24*500 Ml", "500 ml", "Crate", 24, "784.2"),
    ("Taaza 24*500", "500 ml", "Crate", 24, "674.2"),
    ("Taaza 12*1 L", "1 L", "Crate", 12, "662.2"),
    ("Taaza 2*6 L", "6 L", "Crate", 2, "615.8"),
    ("Taaza 70*150 ML", "150 ml", "Crate", 70, "630.0"),

    ("Buttermilk 2 x 6 Ltr. Pouch", "6 L", "Crate", 2, "330.60"),
    ("Pro. Buttermilk 30x400 mL Pouch", "400 ml", "Crate", 30, "405.00"),
    ("Pro. Buttermilk 16x650 mL Pouch", "650 ml", "Crate", 16, "296.00"),
    ("Pro. Masala BM 42x260 mL Pouch", "260 ml", "Crate", 42, "378.00"),
    ("Pro. Tadka Chaas 42x260 mL Pouch", "260 ml", "Crate", 42, "378.00"),
    ("Prolife Butter Milk 12x1 L Pet Bet", "1 L", "Crate", 12, "648.00"),
    ("Masti Dahi Pouch 2x5 Kg Crate", "5 Kg", "Crate", 2, "706.64"),
    ("Masti Dahi Pouch 12x1 Kg Crate", "1 Kg", "Crate", 12, "888.00"),
    ("Lite Dahi Pouch 2x5 Kg Crate", "5 Kg", "Crate", 2, "549.12"),
    ("Dahi Pouch 2x5 Kg Crate", "5 Kg", "Crate", 2, "583.80"),
    ("Meetha Dahi Cup 48x80 gm Crate", "80 gm", "Crate", 48, "408.00"),
    ("Masti Dahi Bucket 6x1 Kg Crate", "1 Kg", "Crate", 6, "621.00"),
    ("Probiotic Dahi Bucket 6x1 Kg Crate", "1 Kg", "Crate", 6, "621.00"),
    ("Masti Dahi Cup 24x200 Gm Carton", "200 gm", "Carton", 24, "525.00"),
    ("Masti Dahi Cup 12x400 Gm Carton", "400 gm", "Carton", 12, "525.00"),
    ("Buffalo Milk Dahi 24x200 Gm Cup", "200 gm", "Crate", 24, "768.00"),
    ("Buffalo Milk Dahi 12x400 Gm Cup", "400 gm", "Crate", 12, "672.00"),
]


def key(value: str) -> str:
    """Normalize whitespace and case for natural-key comparisons."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def get_or_create_agency(name: str) -> Agency:
    """Find an agency case-insensitively or create it."""
    row = next(
        (
            item
            for item in Agency.query.all()
            if key(item.name) == key(name)
        ),
        None,
    )

    if row:
        log.info("Agency already exists: %s", row.name)
        return row

    specification = next(
        item
        for item in AGENCIES
        if key(item["name"]) == key(name)
    )

    row = Agency(**specification)
    db.session.add(row)
    db.session.flush()

    log.info("Created agency: %s", name)
    return row


def run(reset: bool = False) -> None:
    """Seed agencies, dealers, products, and current product prices."""
    with app.app_context():
        settings = BusinessSettings.query.first()

        if not settings:
            db.session.add(
                BusinessSettings(
                    business_name="Dairy Distribution Business"
                )
            )
            db.session.flush()
            log.info("Created business settings")
        else:
            log.info("Business settings already exist")

        configured_username = app.config.get("SEED_ADMIN_USERNAME")

        if configured_username:
            admin = User.query.filter_by(
                username=configured_username
            ).first()
        else:
            admin = User.query.filter_by(role="admin").first()

        if admin:
            log.info("Using admin user: %s", admin.username)
        else:
            log.warning(
                "No admin user found; product prices will have set_by=NULL"
            )

        agencies = {
            item["name"]: get_or_create_agency(item["name"])
            for item in AGENCIES
        }

        if reset:
            for dealer_name, agency_name in DEALERS:
                agency_row = agencies[agency_name]

                dealer = Dealer.query.filter_by(
                    name=dealer_name,
                    agency_id=agency_row.id,
                ).first()

                if dealer:
                    db.session.delete(dealer)

            for product_name, *_ in PRODUCTS:
                product = Product.query.filter_by(
                    name=product_name
                ).first()

                if product:
                    ProductPrice.query.filter_by(
                        product_id=product.id
                    ).delete(synchronize_session=False)

                    db.session.delete(product)

            db.session.flush()
            log.info("Reset owned dealer and product rows")

        for dealer_name, agency_name in DEALERS:
            agency_row = agencies[agency_name]

            dealer = Dealer.query.filter_by(
                name=dealer_name,
                agency_id=agency_row.id,
            ).first()

            if dealer:
                log.info(
                    "Dealer already exists: %s (%s)",
                    dealer_name,
                    agency_name,
                )
                continue

            dealer = Dealer(
                name=dealer_name,
                agency_id=agency_row.id,
                opening_balance=Decimal("0.00"),
                pending_balance=Decimal("0.00"),
                is_active=True,
            )

            db.session.add(dealer)

            log.info(
                "Created dealer: %s (%s)",
                dealer_name,
                agency_name,
            )

        db.session.flush()

        all_products = Product.query.all()

        for display_order, (
            product_name,
            pack_size,
            outer_unit,
            pieces_per_unit,
            price_text,
        ) in enumerate(PRODUCTS, start=1):
            product = next(
                (
                    item
                    for item in all_products
                    if key(item.name) == key(product_name)
                    and (item.pack_size or "") == pack_size
                ),
                None,
            )

            if not product:
                product = Product(
                    name=product_name,
                    pack_size=pack_size,
                    outer_unit=outer_unit,
                    pieces_per_unit=pieces_per_unit,
                    display_order=display_order,
                    is_active=True,
                )

                db.session.add(product)
                db.session.flush()
                all_products.append(product)

                log.info("Created product: %s", product_name)
            else:
                log.info("Product already exists: %s", product_name)

            desired_price = Decimal(price_text)

            current_price = ProductPrice.query.filter_by(
                product_id=product.id,
                effective_to=None,
            ).first()

            if (
                current_price
                and Decimal(str(current_price.price_per_unit))
                == desired_price
            ):
                log.info(
                    "Current RETAILER price unchanged: %s = %s",
                    product_name,
                    desired_price,
                )
                continue

            if current_price:
                current_price.effective_to = datetime.utcnow()
                log.info(
                    "Closed previous price for: %s",
                    product_name,
                )

            db.session.add(
                ProductPrice(
                    product_id=product.id,
                    price_per_unit=desired_price,
                    effective_from=datetime.utcnow(),
                    set_by=admin.id if admin else None,
                )
            )

            log.info(
                "Set RETAILER price: %s = %s",
                product_name,
                desired_price,
            )

        db.session.commit()

        log.info(
            "Seed complete: %d agencies, %d dealers, %d products, %d prices",
            Agency.query.count(),
            Dealer.query.count(),
            Product.query.count(),
            ProductPrice.query.count(),
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed Dairy Manager from the supplied image data."
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Delete and recreate only dealer/product rows represented "
            "by this script; never delete users, agencies, or settings."
        ),
    )

    args = parser.parse_args()

    try:
        run(reset=args.reset)
    except Exception:
        db.session.rollback()
        log.exception("Seed failed; transaction rolled back")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())