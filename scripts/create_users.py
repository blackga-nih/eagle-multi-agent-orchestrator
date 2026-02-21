#!/usr/bin/env python3
"""Create test + admin Cognito users with required tenant attributes."""
import boto3
import sys

REGION = "us-east-1"
STACK_NAME = "EagleCoreStack"

USERS = [
    {
        "email": "testuser@example.com",
        "given": "Test",
        "family": "User",
        "tenant": "nci",
        "tier": "basic",
        "password": "EagleTest2024!",
        "admin": False,
    },
    {
        "email": "admin@example.com",
        "given": "Admin",
        "family": "User",
        "tenant": "nci",
        "tier": "premium",
        "password": "EagleAdmin2024!",
        "admin": True,
    },
]


def get_user_pool_id():
    cf = boto3.client("cloudformation", region_name=REGION)
    stacks = cf.describe_stacks(StackName=STACK_NAME)["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in stacks if o["OutputKey"] == "UserPoolId")


def create_users():
    pool_id = get_user_pool_id()
    print(f"User Pool: {pool_id}")

    cog = boto3.client("cognito-idp", region_name=REGION)

    for u in USERS:
        # Create user
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

        # Set permanent password
        cog.admin_set_user_password(
            UserPoolId=pool_id,
            Username=u["email"],
            Password=u["password"],
            Permanent=True,
        )

        # Admin group
        if u["admin"]:
            group = f"{u['tenant']}-admins"
            try:
                cog.create_group(
                    UserPoolId=pool_id,
                    GroupName=group,
                    Description=f"{u['tenant']} tenant administrators",
                )
                print(f"  Created group: {group}")
            except cog.exceptions.GroupExistsException:
                pass
            cog.admin_add_user_to_group(
                UserPoolId=pool_id,
                Username=u["email"],
                GroupName=group,
            )
            print(f"  Added {u['email']} to {group}")

    print()
    print("Users ready:")
    print("  testuser@example.com / EagleTest2024!  (basic, user)")
    print("  admin@example.com    / EagleAdmin2024! (premium, admin)")


if __name__ == "__main__":
    try:
        create_users()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
