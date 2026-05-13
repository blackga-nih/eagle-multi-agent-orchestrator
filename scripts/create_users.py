#!/usr/bin/env python3
"""Seed test Cognito user(s) and promote named NIH users to nci-admins."""
import boto3
import sys

REGION = "us-east-1"
STACK_NAME = "EagleCoreStack"

USERS = [
    {
        "email": "eagle-qa@nih.gov",
        "given": "Eagle",
        "family": "QA",
        "tenant": "nci",
        "tier": "basic",
        "password": "Eagle2026!",
        "admin": False,
    },
]

# Existing NIH-account users to add to nci-admins (idempotent — only adds to group,
# does not create users; users must already exist in the pool).
ADMIN_PROMOTIONS = [
    "mohommed.hoque@nih.gov", "hoquemi@nih.gov",
    "jitong.li@nih.gov", "lij46@nih.gov",
    "ryan.hash@nih.gov", "hashrg@nih.gov",
    "lata.valisetty@nih.gov", "valisettysl@nih.gov",
    "greg.black@nih.gov", "blackga@nih.gov",
]


def get_user_pool_id():
    cf = boto3.client("cloudformation", region_name=REGION)
    stacks = cf.describe_stacks(StackName=STACK_NAME)["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in stacks if o["OutputKey"] == "UserPoolId")


def find_username_by_email(cog, pool_id, email):
    resp = cog.list_users(UserPoolId=pool_id, Filter=f'email = "{email}"', Limit=1)
    if not resp.get("Users"):
        return None
    return resp["Users"][0]["Username"]


def create_users():
    pool_id = get_user_pool_id()
    print(f"User Pool: {pool_id}")

    cog = boto3.client("cognito-idp", region_name=REGION)

    for u in USERS:
        try:
            cog.admin_create_user(
                UserPoolId=pool_id,
                Username=u["email"],
                UserAttributes=[
                    {"Name": "email", "Value": u["email"]},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "given_name", "Value": u["given"]},
                    {"Name": "family_name", "Value": u["family"]},
                    {"Name": "custom:tenant_id", "Value": u["tenant"]},
                    {"Name": "custom:subscription_tier", "Value": u["tier"]},
                ],
                TemporaryPassword="TempPass123!",
                MessageAction="SUPPRESS",
            )
            print(f"  Created {u['email']}")
        except cog.exceptions.UsernameExistsException:
            print(f"  {u['email']} already exists (skipped)")

        cog.admin_set_user_password(
            UserPoolId=pool_id,
            Username=u["email"],
            Password=u["password"],
            Permanent=True,
        )

    # Ensure nci-admins group exists
    try:
        cog.create_group(
            UserPoolId=pool_id,
            GroupName="nci-admins",
            Description="nci tenant administrators",
        )
        print("  Created group: nci-admins")
    except cog.exceptions.GroupExistsException:
        pass

    print()
    print("Promoting NIH admins:")
    for email in ADMIN_PROMOTIONS:
        username = find_username_by_email(cog, pool_id, email)
        if not username:
            print(f"  SKIP {email} (not in pool — must sign in first)")
            continue
        cog.admin_add_user_to_group(
            UserPoolId=pool_id, Username=username, GroupName="nci-admins"
        )
        # Premium tier so admins get full feature access
        cog.admin_update_user_attributes(
            UserPoolId=pool_id,
            Username=username,
            UserAttributes=[{"Name": "custom:subscription_tier", "Value": "premium"}],
        )
        print(f"  Promoted {email}")

    print()
    print("Users ready:")
    print("  eagle-qa@nih.gov     / Eagle2026!      (basic, user)")
    print(f"  + {len(ADMIN_PROMOTIONS)} NIH admins in nci-admins (premium tier)")


if __name__ == "__main__":
    try:
        create_users()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
