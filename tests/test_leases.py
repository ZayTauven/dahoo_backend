from .factories import DahooTestCase, make_lease, make_unit, make_user


class LeaseLifecycleTests(DahooTestCase):
    def test_create_sets_draft_and_author(self):
        unit = make_unit(self.org_a)
        response = self.api_a.post(
            "/api/v1/leases/",
            {"unit": unit.id, "tenant": make_user().id, "start_date": "2026-01-01", "rent_amount": "150000"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["status"], "DRAFT")
        self.assertEqual(response.json()["created_by"], self.admin_a.id)

    def test_end_date_must_follow_start_date(self):
        unit = make_unit(self.org_a)
        response = self.api_a.post(
            "/api/v1/leases/",
            {"unit": unit.id, "tenant": make_user().id, "start_date": "2026-01-01", "end_date": "2025-12-31", "rent_amount": "1"},
        )
        self.assertEqual(response.status_code, 400)

    def test_activation_rents_the_unit(self):
        lease = make_lease(self.org_a)
        response = self.api_a.post(f"/api/v1/leases/{lease.id}/activate/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ACTIVE")
        self.assertIsNotNone(response.json()["signed_at"])
        lease.unit.refresh_from_db()
        self.assertEqual(lease.unit.status, "RENTED")

    def test_unit_cannot_have_two_active_leases(self):
        first = make_lease(self.org_a, status="ACTIVE")
        second = make_lease(self.org_a, unit=first.unit)
        response = self.api_a.post(f"/api/v1/leases/{second.id}/activate/")
        self.assertEqual(response.status_code, 400)

    def test_invalid_transition_is_400_not_500(self):
        lease = make_lease(self.org_a)
        response = self.api_a.post(f"/api/v1/leases/{lease.id}/terminate/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.json())

    def test_termination_frees_the_unit(self):
        lease = make_lease(self.org_a)
        self.api_a.post(f"/api/v1/leases/{lease.id}/activate/")
        self.api_a.post(f"/api/v1/leases/{lease.id}/terminate/")
        lease.unit.refresh_from_db()
        self.assertEqual(lease.unit.status, "FREE")

    def test_cancelling_a_draft_leaves_unit_untouched(self):
        lease = make_lease(self.org_a, unit=make_unit(self.org_a, status="MAINTENANCE"))
        response = self.api_a.post(f"/api/v1/leases/{lease.id}/cancel/")
        self.assertEqual(response.status_code, 200)
        lease.unit.refresh_from_db()
        self.assertEqual(lease.unit.status, "MAINTENANCE")
