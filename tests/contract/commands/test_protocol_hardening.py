"""Fail-closed and compatibility details of the command envelope."""

import json

import pytest

from niep.application.command import _public_result
from niep.application.commands import CommandProtocolError, CommandRequest, CommandResponse
from niep.domain.result import ResultCode, ServiceResult


@pytest.mark.contract
@pytest.mark.parametrize("request_id", [None, 0, False, ""])
def test_explicit_invalid_request_id_is_rejected(request_id):
    with pytest.raises(CommandProtocolError):
        CommandRequest.from_dict({"command": "status", "request_id": request_id})


@pytest.mark.contract
def test_missing_request_id_is_generated():
    request = CommandRequest.from_dict({"command": "status"})
    assert isinstance(request.request_id, str)
    assert request.request_id


@pytest.mark.contract
def test_protocol_only_response_codes_round_trip_to_service_result():
    result = CommandResponse.failure("request-1", "invalid_request", "bad envelope").to_service_result()
    assert result.code == ResultCode.INVALID_REQUEST

    extension = CommandResponse.failure("request-2", "future_code", "unsupported extension").to_service_result()
    assert extension.code == "future_code"
    json.dumps(extension.to_dict())


@pytest.mark.contract
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_command_data_is_rejected(value):
    with pytest.raises(CommandProtocolError):
        CommandRequest("status", options={"value": value})


@pytest.mark.contract
def test_non_string_mapping_key_fails_closed_without_stringifying_secret():
    class SecretKey:
        def __str__(self):
            return "secret-key=do-not-leak"

    with pytest.raises(CommandProtocolError):
        CommandRequest("status", options={SecretKey(): "value"})
    result = _public_result(
        ServiceResult(ok=True, code=ResultCode.STATUS, data={SecretKey(): "value"})
    )
    assert result.code is ResultCode.COMMAND_ERROR
    assert "secret-key" not in str(result.to_dict())


@pytest.mark.contract
def test_non_string_envelope_key_fails_before_unknown_field_formatting():
    class SecretKey:
        def __str__(self):
            return "envelope-secret=do-not-leak"

    with pytest.raises(CommandProtocolError) as request_error:
        CommandRequest.from_dict({SecretKey(): "value"})
    assert "envelope-secret" not in str(request_error.value)

    with pytest.raises(CommandProtocolError) as response_error:
        CommandResponse.from_dict({SecretKey(): "value"})
    assert "envelope-secret" not in str(response_error.value)


@pytest.mark.contract
def test_legacy_service_result_is_json_safe_without_stringifying_objects():
    class Secret:
        def __str__(self):
            return "service-secret=do-not-leak"

    payload = ServiceResult(ok=True, code=ResultCode.STATUS, data=Secret()).to_dict()
    assert payload["data"] is None
    assert "service-secret" not in str(payload)
    json.dumps(payload)
