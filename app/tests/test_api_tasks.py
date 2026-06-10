from __future__ import annotations

from technical_document_ml_service.db.session import SessionLocal
from technical_document_ml_service.services.prediction_processing_service import (
    process_document_prediction_task,
)
from helpers import submit_test_task


def test_get_tasks_returns_user_tasks_list(
    client,
    api_user,
    api_model,
    auth_headers,
    publish_task_spy,
) -> None:
    first_submission = submit_test_task(api_user, api_model, "passport_fields")
    second_submission = submit_test_task(api_user, api_model, "certificate_fields")

    response = client.get(
        "/tasks",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()

    assert body["limit"] == 50
    assert body["offset"] == 0
    assert body["status"] is None
    assert len(body["items"]) == 2

    returned_ids = {item["id"] for item in body["items"]}
    assert str(first_submission.task_id) in returned_ids
    assert str(second_submission.task_id) in returned_ids

    first_item = body["items"][0]
    assert first_item["model_name"] == api_model.name
    assert first_item["backend_name"] == "docling"
    assert first_item["status"] == "queued"
    assert first_item["documents_count"] == 1
    assert first_item["first_document_name"] == "sample.pdf"


def test_get_tasks_supports_status_filter(
    client,
    api_user,
    api_model,
    auth_headers,
    publish_task_spy,
) -> None:
    queued_submission = submit_test_task(api_user, api_model, "queued_schema")
    completed_submission = submit_test_task(api_user, api_model, "completed_schema")

    with SessionLocal() as session:
        process_document_prediction_task(
            session,
            task_id=completed_submission.task_id,
        )

    response = client.get(
        "/tasks?status=completed",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "completed"
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(completed_submission.task_id)
    assert body["items"][0]["status"] == "completed"

    response = client.get(
        "/tasks?status=queued",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "queued"
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(queued_submission.task_id)
    assert body["items"][0]["status"] == "queued"


def test_get_task_details_returns_task_payload(
    client,
    api_user,
    api_model,
    auth_headers,
    publish_task_spy,
) -> None:
    submission = submit_test_task(api_user, api_model)

    response = client.get(
        f"/tasks/{submission.task_id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()

    assert body["id"] == str(submission.task_id)
    assert body["user_id"] == str(api_user.id)
    assert body["model_id"] == str(api_model.id)
    assert body["model_name"] == api_model.name
    assert body["backend_name"] == "docling"
    assert body["target_schema"] == "passport_fields"
    assert body["status"] == "queued"
    assert body["result_id"] is None
    assert len(body["documents"]) == 1
    assert body["documents"][0]["original_filename"] == "sample.pdf"


def test_get_task_result_returns_null_result_for_queued_task(
    client,
    api_user,
    api_model,
    auth_headers,
    publish_task_spy,
) -> None:
    submission = submit_test_task(api_user, api_model)

    response = client.get(
        f"/tasks/{submission.task_id}/result",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()

    assert body["task"]["id"] == str(submission.task_id)
    assert body["task"]["status"] == "queued"
    assert body["result"] is None
    assert body["artifacts"] == []
    assert body["has_result"] is False


def test_get_task_result_returns_result_and_artifacts_after_processing(
    client,
    api_user,
    api_model,
    auth_headers,
    publish_task_spy,
) -> None:
    submission = submit_test_task(api_user, api_model)

    with SessionLocal() as session:
        process_document_prediction_task(
            session,
            task_id=submission.task_id,
        )

    response = client.get(
        f"/tasks/{submission.task_id}/result",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()

    assert body["task"]["id"] == str(submission.task_id)
    assert body["task"]["status"] == "completed"
    assert body["has_result"] is True
    assert body["result"] is not None
    assert body["result"]["task_id"] == str(submission.task_id)
    assert body["result"]["output_path"] is not None
    assert body["result"]["artifacts_dir"] is not None
    assert "sample.pdf" in body["result"]["extracted_data"]
    assert len(body["artifacts"]) >= 1


def test_download_task_artifact_streams_file_from_storage(
    client,
    api_user,
    api_model,
    auth_headers,
    publish_task_spy,
) -> None:
    submission = submit_test_task(api_user, api_model)

    with SessionLocal() as session:
        process_document_prediction_task(
            session,
            task_id=submission.task_id,
        )

    result = client.get(
        f"/tasks/{submission.task_id}/result",
        headers=auth_headers,
    ).json()
    artifact_name = result["artifacts"][0]["name"]

    response = client.get(
        f"/tasks/{submission.task_id}/artifacts/{artifact_name}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert artifact_name in response.headers["content-disposition"]
    assert len(response.content) > 0


def test_download_unknown_task_artifact_returns_404(
    client,
    api_user,
    api_model,
    auth_headers,
    publish_task_spy,
) -> None:
    submission = submit_test_task(api_user, api_model)

    with SessionLocal() as session:
        process_document_prediction_task(
            session,
            task_id=submission.task_id,
        )

    response = client.get(
        f"/tasks/{submission.task_id}/artifacts/does-not-exist.json",
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_get_task_details_for_foreign_user_returns_403(
    client,
    api_user,
    api_model,
    low_balance_user,
    low_balance_auth_headers,
    publish_task_spy,
) -> None:
    submission = submit_test_task(api_user, api_model)

    response = client.get(
        f"/tasks/{submission.task_id}",
        headers=low_balance_auth_headers,
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "forbidden"


def test_get_tasks_does_not_return_foreign_user_tasks(
    client,
    api_user,
    another_api_user,
    api_model,
    auth_headers,
    another_auth_headers,
    publish_task_spy,
) -> None:
    own_submission = submit_test_task(api_user, api_model, "own_schema")
    submit_test_task(another_api_user, api_model, "foreign_schema")

    response = client.get(
        "/tasks",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()

    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(own_submission.task_id)