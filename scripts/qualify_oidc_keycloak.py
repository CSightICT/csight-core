#!/usr/bin/env python3
"""Exercise the isolated Keycloak OIDC qualification flow without a browser profile."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

API_BASE = "http://127.0.0.1:18000"
IDP_BASE = "http://localhost:18080"
REALM = "csight-qualification"
USERNAME = "reviewer@csight.demo"


class _LoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self._inside_login_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("id") == "kc-form-login":
            self.action = values.get("action")
            self._inside_login_form = True
        if tag == "input" and self._inside_login_form:
            name = values.get("name")
            if name:
                self.fields[name] = values.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._inside_login_form:
            self._inside_login_form = False


@dataclass(slots=True)
class LoginAttempt:
    opener: Any
    terminal_status: int
    terminal_url: str
    terminal_body: bytes


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _open(opener: Any, request: str | Request) -> tuple[int, str, bytes]:
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, response.geturl(), response.read()
    except HTTPError as error:
        return error.code, error.geturl(), error.read()


def _login(password: str, *, return_path: str = "/cases") -> LoginAttempt:
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    status, login_url, body = _open(
        opener,
        f"{API_BASE}/auth/oidc/login?{urlencode({'return_path': return_path})}",
    )
    if status != 200 or not login_url.startswith(f"{IDP_BASE}/realms/{REALM}/"):
        raise AssertionError(f"unexpected provider login response: {status} {login_url}")
    # Browsers treat localhost as a trustworthy context and return Secure cookies
    # during local development.  Python's CookieJar does not, so mirror that
    # browser behavior only for this explicit localhost-only qualification stack.
    for cookie in cookie_jar:
        if cookie.secure and cookie.domain in {"localhost", "localhost.local"}:
            cookie.secure = False
    parser = _LoginFormParser()
    parser.feed(body.decode("utf-8"))
    if not parser.action:
        raise AssertionError("Keycloak login form was not found")
    fields = {**parser.fields, "username": USERNAME, "password": password}
    request = Request(
        parser.action,
        data=urlencode(fields).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    terminal_status, terminal_url, terminal_body = _open(opener, request)
    return LoginAttempt(
        opener=opener,
        terminal_status=terminal_status,
        terminal_url=terminal_url,
        terminal_body=terminal_body,
    )


def _json_request(
    opener: Any,
    url: str,
    *,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    request_headers = {"Accept": "application/json", **(headers or {})}
    body: bytes | None = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    status, _final_url, response_body = _open(
        opener,
        Request(url, data=body, headers=request_headers, method=method),
    )
    parsed: Any = None
    if response_body:
        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError:
            parsed = response_body.decode("utf-8", errors="replace")
    return status, parsed


def _admin_token(username: str, password: str) -> str:
    request = Request(
        f"{IDP_BASE}/realms/master/protocol/openid-connect/token",
        data=urlencode(
            {
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": username,
                "password": password,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        payload = json.load(response)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise AssertionError("Keycloak admin token was not issued")
    return token


def _admin_request(
    token: str,
    path: str,
    *,
    method: str = "GET",
    data: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    return _json_request(
        build_opener(),
        f"{IDP_BASE}/admin/realms/{REALM}{path}",
        method=method,
        data=data,
        headers={"Authorization": f"Bearer {token}"},
    )


def _one(items: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise AssertionError(f"expected exactly one {label}")
    return items[0]


def _session(opener: Any) -> tuple[int, Any]:
    return _json_request(opener, f"{API_BASE}/auth/session")


def main() -> int:
    user_password = _required_env("OIDC_QUALIFICATION_USER_PASSWORD")
    admin_user = _required_env("OIDC_QUALIFICATION_ADMIN_USER")
    admin_password = _required_env("OIDC_QUALIFICATION_ADMIN_PASSWORD")
    results: dict[str, Any] = {
        "qualification": "keycloak-authorization-code-pkce",
        "realm": REALM,
    }

    capabilities_status, capabilities = _json_request(
        build_opener(), f"{API_BASE}/auth/capabilities"
    )
    results["oidc_only"] = capabilities_status == 200 and capabilities == {
        "oidc_enabled": True,
        "legacy_password_enabled": False,
    }
    legacy_status, _legacy = _json_request(
        build_opener(), f"{API_BASE}/api/v1/auth/token", method="POST"
    )
    results["legacy_token_route_absent"] = legacy_status == 404

    initial = _login(user_password, return_path="/cases")
    session_status, session = _session(initial.opener)
    results["pkce_login"] = session_status == 200
    results["return_path_preserved"] = initial.terminal_url == f"{API_BASE}/cases"
    results["mapped_role"] = (
        session_status == 200
        and session["principal"]["email"] == USERNAME
        and session["principal"]["roles"] == ["REVIEWER"]
    )

    missing_csrf_status, _ = _json_request(initial.opener, f"{API_BASE}/auth/logout", method="POST")
    valid_csrf_status, _ = _json_request(
        initial.opener,
        f"{API_BASE}/auth/logout",
        method="POST",
        headers={"X-CSRF-Token": session["csrf_token"]},
    )
    logged_out_status, _ = _session(initial.opener)
    results["csrf_rejected_without_token"] = missing_csrf_status == 403
    results["csrf_logout"] = valid_csrf_status == 204 and logged_out_status == 401

    active = _login(user_password)
    active_status, _ = _session(active.opener)
    if active_status != 200:
        raise AssertionError("second login did not create an active session")

    admin_token = _admin_token(admin_user, admin_password)
    users_status, users = _admin_request(
        admin_token,
        f"/users?{urlencode({'username': USERNAME, 'exact': 'true'})}",
    )
    groups_status, groups = _admin_request(
        admin_token,
        f"/groups?{urlencode({'search': 'csight-reviewers', 'exact': 'true'})}",
    )
    if users_status != 200 or groups_status != 200:
        raise AssertionError("Keycloak qualification subject lookup failed")
    user = _one(users, label="qualification user")
    group = _one(groups, label="qualification group")
    user_id = user["id"]
    group_id = group["id"]

    group_removed = False
    user_disabled = False
    try:
        remove_status, _ = _admin_request(
            admin_token,
            f"/users/{user_id}/groups/{group_id}",
            method="DELETE",
        )
        group_removed = remove_status == 204
        denied_group_login = _login(user_password)
        denied_group_status, _ = _session(denied_group_login.opener)
        results["group_removal_blocks_new_login"] = denied_group_status == 401
        group_logout_status, _ = _admin_request(
            admin_token,
            f"/users/{user_id}/logout",
            method="POST",
        )
        existing_after_group_status, _ = _session(active.opener)
        results["group_removal_revokes_existing_session"] = (
            group_logout_status == 204 and existing_after_group_status == 401
        )

        restore_group_status, _ = _admin_request(
            admin_token,
            f"/users/{user_id}/groups/{group_id}",
            method="PUT",
        )
        if restore_group_status != 204:
            raise AssertionError("failed to restore qualification group")
        group_removed = False

        account_active = _login(user_password)
        account_active_status, _ = _session(account_active.opener)
        if account_active_status != 200:
            raise AssertionError("login before account disable did not create a session")

        latest_status, latest_user = _admin_request(admin_token, f"/users/{user_id}")
        if latest_status != 200 or not isinstance(latest_user, dict):
            raise AssertionError("failed to read qualification user")
        disabled_user = {**latest_user, "enabled": False}
        disable_status, _ = _admin_request(
            admin_token,
            f"/users/{user_id}",
            method="PUT",
            data=disabled_user,
        )
        user_disabled = disable_status == 204
        denied_account_login = _login(user_password)
        denied_account_status, _ = _session(denied_account_login.opener)
        results["disabled_account_blocks_new_login"] = denied_account_status == 401
        account_logout_status, _ = _admin_request(
            admin_token,
            f"/users/{user_id}/logout",
            method="POST",
        )
        existing_after_disable_status, _ = _session(account_active.opener)
        results["disabled_account_revokes_existing_session"] = (
            account_logout_status == 204 and existing_after_disable_status == 401
        )
    finally:
        if group_removed:
            _admin_request(
                admin_token,
                f"/users/{user_id}/groups/{group_id}",
                method="PUT",
            )
        if user_disabled:
            latest_status, latest_user = _admin_request(admin_token, f"/users/{user_id}")
            if latest_status == 200 and isinstance(latest_user, dict):
                _admin_request(
                    admin_token,
                    f"/users/{user_id}",
                    method="PUT",
                    data={**latest_user, "enabled": True},
                )

    expiring = _login(user_password)
    time.sleep(13)
    expired_status, _ = _session(expiring.opener)
    results["idle_expiry"] = expired_status == 401

    required = (
        "oidc_only",
        "legacy_token_route_absent",
        "pkce_login",
        "return_path_preserved",
        "mapped_role",
        "csrf_rejected_without_token",
        "csrf_logout",
        "group_removal_blocks_new_login",
        "group_removal_revokes_existing_session",
        "disabled_account_blocks_new_login",
        "disabled_account_revokes_existing_session",
        "idle_expiry",
    )
    failed = [name for name in required if results.get(name) is not True]
    results["failed_gates"] = failed
    results["verdict"] = "PASS" if not failed else "BLOCKED"
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # qualification evidence must fail closed
        print(
            json.dumps(
                {
                    "qualification": "keycloak-authorization-code-pkce",
                    "verdict": "ERROR",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from error
