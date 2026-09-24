"""Photos des annonces : envoi, validation (format, taille, nombre), modification, cloisonnement."""

import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from listings.models import ListingPhoto
from listings.photos import MAX_PHOTO_SIZE, MAX_PHOTOS_PER_LISTING

from .factories import DahooTestCase, add_member, client_for, image_file, make_listing, results


class ListingPhotoTests(DahooTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Fichiers envoyés écrits dans un dossier temporaire, supprimé après les tests.
        media_root = tempfile.mkdtemp(prefix="dahoo-test-media-")
        cls.addClassCleanup(shutil.rmtree, media_root, ignore_errors=True)
        cls.enterClassContext(override_settings(MEDIA_ROOT=media_root))

    def setUp(self):
        super().setUp()
        self.listing = make_listing(self.org_a, status="DRAFT")
        self.url = f"/api/v1/listings/{self.listing.id}/photos/"

    def upload(self, client=None, **fields):
        fields.setdefault("image", image_file())
        return (client or self.api_a).post(self.url, fields, format="multipart")

    def test_upload_returns_absolute_url_and_orders_photos(self):
        first = self.upload(alt="Façade")
        self.assertEqual(first.status_code, 201, first.content)
        data = first.json()
        self.assertTrue(data["url"].startswith("http://testserver/media/listings/"), data["url"])
        self.assertNotIn("image", data)
        self.assertEqual((data["alt"], data["position"]), ("Façade", 0))
        stored = ListingPhoto.objects.get(pk=data["id"]).image
        self.assertTrue(Path(stored.path).is_file())

        second = self.upload(image=image_file("salon.webp", "WEBP")).json()
        self.assertEqual(second["position"], 1)
        listed = self.api_a.get(self.url).json()
        self.assertEqual([photo["id"] for photo in listed], [data["id"], second["id"]])

    def test_jpeg_is_accepted(self):
        self.assertEqual(self.upload(image=image_file("photo.jpg", "JPEG")).status_code, 201)

    def test_other_formats_are_refused(self):
        gif = self.upload(image=image_file("anim.gif", "GIF"))
        self.assertEqual(gif.status_code, 400)
        self.assertIn("JPEG, PNG ou WebP", str(gif.json()["image"]))
        text = self.upload(image=SimpleUploadedFile("photo.png", b"pas une image", content_type="image/png"))
        self.assertEqual(text.status_code, 400)
        self.assertFalse(ListingPhoto.objects.exists())

    def test_too_large_image_is_refused(self):
        response = self.upload(image=image_file(padding=MAX_PHOTO_SIZE))
        self.assertEqual(response.status_code, 400)
        self.assertIn("8 Mo", str(response.json()["image"]))

    def test_photo_limit_per_listing(self):
        ListingPhoto.objects.bulk_create(
            ListingPhoto(listing=self.listing, image=f"listings/2026/09/p{i}.png", position=i)
            for i in range(MAX_PHOTOS_PER_LISTING)
        )
        response = self.upload()
        self.assertEqual(response.status_code, 400)
        self.assertIn("20 photos maximum", str(response.json()))

    def test_update_and_delete(self):
        photo = self.upload().json()
        detail = f"/api/v1/listings/photos/{photo['id']}/"
        response = self.api_a.patch(detail, {"alt": "Cuisine", "position": 5}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["alt"], response.json()["position"]), ("Cuisine", 5))
        self.assertEqual(self.api_a.put(detail, {"alt": "x"}, format="json").status_code, 405)

        path = Path(ListingPhoto.objects.get(pk=photo["id"]).image.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.api_a.delete(detail).status_code, 204)
        self.assertFalse(ListingPhoto.objects.exists())
        self.assertFalse(path.exists())

    def test_agency_listing_exposes_cover_and_count(self):
        first = self.upload().json()
        self.upload()
        listing = results(self.api_a.get("/api/v1/listings/"))[0]
        self.assertEqual(listing["cover"], first["url"])
        self.assertEqual(listing["photos_count"], 2)
        self.assertEqual(listing["unit_label"], f"Résidence · Bâtiment A · {self.listing.unit.reference}")

    def test_isolation_between_agencies(self):
        photo = self.upload().json()
        detail = f"/api/v1/listings/photos/{photo['id']}/"
        self.assertEqual(self.api_b.get(self.url).status_code, 404)
        self.assertEqual(self.upload(client=self.api_b).status_code, 404)
        self.assertEqual(self.api_b.get(detail).status_code, 404)
        self.assertEqual(self.api_b.patch(detail, {"alt": "pirate"}, format="json").status_code, 404)
        self.assertEqual(self.api_b.delete(detail).status_code, 404)
        self.assertEqual(ListingPhoto.objects.get(pk=photo["id"]).alt, "")

    def test_capabilities(self):
        photo = self.upload().json()
        viewer = client_for(add_member(self.org_a, role="VIEWER"))
        self.assertEqual(viewer.get(self.url).status_code, 200)
        self.assertEqual(self.upload(client=viewer).status_code, 403)
        detail = f"/api/v1/listings/photos/{photo['id']}/"
        self.assertEqual(viewer.patch(detail, {"alt": "x"}, format="json").status_code, 403)
        self.assertEqual(viewer.delete(detail).status_code, 403)
