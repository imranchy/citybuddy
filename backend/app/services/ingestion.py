from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ingestion import (
    build_candidate_fingerprint,
    ValidationFinding,
    validate_image_candidate,
    validate_place_candidate,
    validation_status,
)
from app.models.ingestion import (
    ImagePromotionBatch,
    ImageValidationIssue,
    IngestionRun,
    PromotionBatch,
    StagedPlace,
    StagedPlaceImage,
    ValidationIssue,
)
from app.models.place import Place
from app.models.place_image import PlaceImage


def create_ingestion_run(
    database: Session,
    *,
    source: str,
    city: str,
    category: str | None,
    trigger: str,
) -> IngestionRun:
    run = IngestionRun(
        source=source,
        city=city,
        category=category,
        trigger=trigger,
        status="running",
        preview_only=False,
        statistics={},
    )
    database.add(run)
    database.commit()
    database.refresh(run)
    return run


def stage_place_candidates(
    database: Session,
    run: IngestionRun,
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    counts = {"fetched": 0, "valid": 0, "review_required": 0, "invalid": 0}

    candidate_list = [dict(item) for item in candidates]
    name_counts: dict[tuple[str, str], int] = {}
    for candidate in candidate_list:
        key = (
            str(candidate.get("category") or ""),
            str(candidate.get("name") or "").strip().casefold(),
        )
        name_counts[key] = name_counts.get(key, 0) + 1

    for candidate in candidate_list:
        counts["fetched"] += 1
        findings = validate_place_candidate(candidate)
        key = (
            str(candidate.get("category") or ""),
            str(candidate.get("name") or "").strip().casefold(),
        )
        if key[1] and name_counts.get(key, 0) > 1:
            findings.append(
                ValidationFinding(
                    "duplicate_name_in_run",
                    "warning",
                    "Multiple source records in this run share the same name and category.",
                    "name",
                )
            )

        existing_same_name = database.scalar(
            select(Place.id)
            .where(
                func.lower(func.trim(Place.name)) == key[1],
                Place.category == key[0],
                ~(
                    (Place.source == str(candidate.get("source") or ""))
                    & (Place.source_id == str(candidate.get("source_id") or ""))
                ),
            )
            .limit(1)
        )
        if existing_same_name is not None:
            findings.append(
                ValidationFinding(
                    "possible_existing_duplicate",
                    "warning",
                    "A production place already has this name and category.",
                    "name",
                )
            )
        status = validation_status(findings)
        counts[status] += 1

        latitude = candidate.get("latitude")
        longitude = candidate.get("longitude")
        staged_place = StagedPlace(
            ingestion_run_id=run.id,
            source=str(candidate.get("source") or "unknown"),
            source_id=str(candidate.get("source_id") or "missing"),
            name=candidate.get("name") or "",
            category=candidate.get("category") or "",
            description=candidate.get("description"),
            address=candidate.get("address") or "Address unavailable",
            city=candidate.get("city") or "",
            country_code=candidate.get("country_code") or "",
            latitude=(
                float(latitude) if isinstance(latitude, (int, float)) else 0.0
            ),
            longitude=(
                float(longitude) if isinstance(longitude, (int, float)) else 0.0
            ),
            price_level=candidate.get("price_level"),
            rating=candidate.get("rating"),
            dietary_options=list(candidate.get("dietary_options") or []),
            opening_hours=candidate.get("opening_hours"),
            website=candidate.get("website"),
            operator=candidate.get("operator"),
            source_payload=dict(candidate.get("source_payload") or {}),
            fingerprint=build_candidate_fingerprint(candidate),
            validation_status=status,
            promotion_status="pending",
        )
        database.add(staged_place)
        database.flush()

        for finding in findings:
            database.add(
                ValidationIssue(
                    staged_place_id=staged_place.id,
                    code=finding.code,
                    severity=finding.severity,
                    field=finding.field,
                    message=finding.message,
                )
            )

    run.status = "completed"
    run.statistics = counts
    run.completed_at = datetime.now(timezone.utc)
    database.commit()
    return counts


def fail_ingestion_run(
    database: Session,
    run: IngestionRun,
    error: Exception,
) -> None:
    run.status = "failed"
    run.error_message = str(error)[:4000]
    run.completed_at = datetime.now(timezone.utc)
    database.commit()


def stage_image_candidates(
    database: Session,
    run: IngestionRun,
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    counts = {"fetched": 0, "valid": 0, "review_required": 0, "invalid": 0}

    for candidate_mapping in candidates:
        candidate = dict(candidate_mapping)
        counts["fetched"] += 1
        findings = validate_image_candidate(candidate)
        status = validation_status(findings)
        counts[status] += 1

        staged_image = StagedPlaceImage(
            ingestion_run_id=run.id,
            place_id=int(candidate.get("place_id") or 0),
            wikidata_id=str(candidate.get("wikidata_id") or "missing"),
            source=str(candidate.get("source") or "unknown"),
            source_image_id=str(candidate.get("source_image_id") or "missing"),
            image_url=str(candidate.get("image_url") or ""),
            thumbnail_url=candidate.get("thumbnail_url"),
            source_page_url=str(candidate.get("source_page_url") or ""),
            attribution=str(candidate.get("attribution") or ""),
            license=str(candidate.get("license") or ""),
            license_url=candidate.get("license_url"),
            source_payload=dict(candidate.get("source_payload") or {}),
            fingerprint=build_candidate_fingerprint(candidate),
            validation_status=status,
            promotion_status="pending",
        )
        database.add(staged_image)
        database.flush()

        for finding in findings:
            database.add(
                ImageValidationIssue(
                    staged_image_id=staged_image.id,
                    code=finding.code,
                    severity=finding.severity,
                    field=finding.field,
                    message=finding.message,
                )
            )

    run.status = "completed"
    run.statistics = counts
    run.completed_at = datetime.now(timezone.utc)
    database.commit()
    return counts


def promote_staged_places(
    database: Session,
    *,
    staged_ids: list[int],
    approve_warnings: bool = False,
) -> PromotionBatch:
    if not staged_ids:
        raise ValueError("At least one staged place ID is required.")
    if len(staged_ids) != len(set(staged_ids)):
        raise ValueError("Staged place IDs must not be repeated.")

    staged_places = database.scalars(
        select(StagedPlace)
        .where(StagedPlace.id.in_(staged_ids))
        .with_for_update()
    ).all()

    found_ids = {place.id for place in staged_places}
    missing_ids = sorted(set(staged_ids) - found_ids)
    if missing_ids:
        raise ValueError(f"Unknown staged place IDs: {missing_ids}.")

    run_ids = {place.ingestion_run_id for place in staged_places}
    if len(run_ids) != 1:
        raise ValueError("A promotion batch must belong to one ingestion run.")

    for staged_place in staged_places:
        if staged_place.promotion_status != "pending":
            raise ValueError(
                f"Staged place {staged_place.id} is not pending promotion."
            )
        if staged_place.validation_status == "invalid":
            raise ValueError(
                f"Staged place {staged_place.id} failed validation."
            )
        if (
            staged_place.validation_status == "review_required"
            and not approve_warnings
        ):
            raise ValueError(
                f"Staged place {staged_place.id} requires explicit warning approval."
            )

    batch = PromotionBatch(
        ingestion_run_id=run_ids.pop(),
        status="running",
        requested_staged_ids=staged_ids,
        promoted_count=0,
        skipped_count=0,
    )
    database.add(batch)
    database.commit()
    database.refresh(batch)
    batch_id = batch.id

    try:
        staged_places = database.scalars(
            select(StagedPlace)
            .where(StagedPlace.id.in_(staged_ids))
            .with_for_update()
        ).all()

        for staged_place in staged_places:
            if staged_place.promotion_status != "pending":
                raise ValueError(
                    f"Staged place {staged_place.id} changed during promotion."
                )

        for staged_place in staged_places:
            existing_place = database.scalar(
                select(Place).where(
                    Place.source == staged_place.source,
                    Place.source_id == staged_place.source_id,
                )
            )
            if existing_place is not None:
                staged_place.promotion_status = "skipped"
                staged_place.promoted_place_id = existing_place.id
                batch.skipped_count += 1
                continue

            place = Place(
                source=staged_place.source,
                source_id=staged_place.source_id,
                name=staged_place.name,
                category=staged_place.category,
                description=staged_place.description,
                address=staged_place.address,
                city=staged_place.city,
                country_code=staged_place.country_code,
                location=WKTElement(
                    f"POINT({staged_place.longitude} {staged_place.latitude})",
                    srid=4326,
                ),
                price_level=staged_place.price_level,
                rating=staged_place.rating,
                dietary_options=staged_place.dietary_options,
                opening_hours=staged_place.opening_hours,
                website=staged_place.website,
                operator=staged_place.operator,
            )
            database.add(place)
            database.flush()
            staged_place.promotion_status = "promoted"
            staged_place.promoted_place_id = place.id
            batch.promoted_count += 1

        batch.status = "completed"
        batch.completed_at = datetime.now(timezone.utc)
        database.commit()
        database.refresh(batch)
        return batch
    except Exception as error:
        database.rollback()
        failed_batch = database.get(PromotionBatch, batch_id)
        if failed_batch is not None:
            failed_batch.status = "failed"
            failed_batch.error_message = str(error)[:4000]
            failed_batch.completed_at = datetime.now(timezone.utc)
            database.commit()
        raise


def promote_staged_images(
    database: Session,
    *,
    staged_ids: list[int],
) -> ImagePromotionBatch:
    if not staged_ids:
        raise ValueError("At least one staged image ID is required.")
    if len(staged_ids) != len(set(staged_ids)):
        raise ValueError("Staged image IDs must not be repeated.")

    staged_images = database.scalars(
        select(StagedPlaceImage).where(StagedPlaceImage.id.in_(staged_ids))
    ).all()
    found_ids = {image.id for image in staged_images}
    missing_ids = sorted(set(staged_ids) - found_ids)
    if missing_ids:
        raise ValueError(f"Unknown staged image IDs: {missing_ids}.")

    run_ids = {image.ingestion_run_id for image in staged_images}
    if len(run_ids) != 1:
        raise ValueError("An image promotion batch must belong to one ingestion run.")

    for staged_image in staged_images:
        if staged_image.promotion_status != "pending":
            raise ValueError(
                f"Staged image {staged_image.id} is not pending promotion."
            )
        if staged_image.validation_status != "valid":
            raise ValueError(
                f"Staged image {staged_image.id} did not pass validation."
            )

    batch = ImagePromotionBatch(
        ingestion_run_id=run_ids.pop(),
        status="running",
        requested_staged_ids=staged_ids,
        promoted_count=0,
        skipped_count=0,
    )
    database.add(batch)
    database.commit()
    database.refresh(batch)
    batch_id = batch.id

    try:
        staged_images = database.scalars(
            select(StagedPlaceImage)
            .where(StagedPlaceImage.id.in_(staged_ids))
            .with_for_update()
        ).all()

        for staged_image in staged_images:
            if staged_image.promotion_status != "pending":
                raise ValueError(
                    f"Staged image {staged_image.id} changed during promotion."
                )

            existing_image = database.scalar(
                select(PlaceImage).where(
                    PlaceImage.place_id == staged_image.place_id,
                    PlaceImage.source == staged_image.source,
                )
            )
            if existing_image is not None:
                staged_image.promotion_status = "skipped"
                staged_image.promoted_image_id = existing_image.id
                batch.skipped_count += 1
                continue

            has_any_image = database.scalar(
                select(PlaceImage.id)
                .where(PlaceImage.place_id == staged_image.place_id)
                .limit(1)
            ) is not None
            image = PlaceImage(
                place_id=staged_image.place_id,
                source=staged_image.source,
                source_image_id=staged_image.source_image_id,
                image_url=staged_image.image_url,
                thumbnail_url=staged_image.thumbnail_url,
                source_page_url=staged_image.source_page_url,
                attribution=staged_image.attribution,
                license=staged_image.license,
                license_url=staged_image.license_url,
                is_primary=not has_any_image,
            )
            database.add(image)
            database.flush()
            staged_image.promotion_status = "promoted"
            staged_image.promoted_image_id = image.id
            batch.promoted_count += 1

        batch.status = "completed"
        batch.completed_at = datetime.now(timezone.utc)
        database.commit()
        database.refresh(batch)
        return batch
    except Exception as error:
        database.rollback()
        failed_batch = database.get(ImagePromotionBatch, batch_id)
        if failed_batch is not None:
            failed_batch.status = "failed"
            failed_batch.error_message = str(error)[:4000]
            failed_batch.completed_at = datetime.now(timezone.utc)
            database.commit()
        raise
