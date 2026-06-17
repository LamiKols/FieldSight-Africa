"""Link an existing FieldSight user to a partner organization.

This script intentionally does not create a new login account. Create the user
through the existing app registration flow first, then run this script.
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app import app, db  # noqa: E402
from models import PARTNER_ROLES, PartnerOrganization, PartnerUserProfile, User  # noqa: E402


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "partner-organization"


def parse_args():
    parser = argparse.ArgumentParser(description="Create or update a partner profile for an existing user.")
    parser.add_argument("--email", required=True, help="Existing user email address.")
    parser.add_argument("--org-name", required=True, help="Partner organization name.")
    parser.add_argument("--org-slug", help="Partner organization slug. Defaults to a slug from org name.")
    parser.add_argument("--role", required=True, choices=PARTNER_ROLES, help="Partner role to assign.")
    parser.add_argument("--org-status", default="active", help="Partner organization status.")
    parser.add_argument("--profile-status", default="active", help="Partner user profile status.")
    parser.add_argument("--contact-name", help="Partner organization contact name.")
    parser.add_argument("--contact-email", help="Partner organization contact email.")
    parser.add_argument("--contact-phone", help="Partner organization contact phone.")
    return parser.parse_args()


def main():
    args = parse_args()
    email = args.email.strip().lower()
    org_slug = args.org_slug.strip().lower() if args.org_slug else slugify(args.org_name)

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            raise SystemExit(f"No existing user found for {email}. Register the user first.")

        organization = PartnerOrganization.query.filter_by(slug=org_slug).first()
        if not organization:
            organization = PartnerOrganization(
                name=args.org_name.strip(),
                slug=org_slug,
                contact_name=args.contact_name,
                contact_email=args.contact_email,
                contact_phone=args.contact_phone,
                status=args.org_status,
            )
            db.session.add(organization)
            db.session.flush()
        else:
            organization.name = args.org_name.strip()
            organization.status = args.org_status
            if args.contact_name:
                organization.contact_name = args.contact_name
            if args.contact_email:
                organization.contact_email = args.contact_email
            if args.contact_phone:
                organization.contact_phone = args.contact_phone

        profile = PartnerUserProfile.query.filter_by(
            user_id=user.id,
            partner_organization_id=organization.id,
        ).first()
        if not profile:
            profile = PartnerUserProfile(
                user_id=user.id,
                partner_organization_id=organization.id,
                partner_role=args.role,
                status=args.profile_status,
            )
            db.session.add(profile)
        else:
            profile.partner_role = args.role
            profile.status = args.profile_status

        db.session.commit()

        print(f"Linked {user.email} to {organization.name} as {profile.partner_role} ({profile.status}).")


if __name__ == "__main__":
    main()
