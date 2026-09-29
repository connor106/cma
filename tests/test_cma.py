"""Offline tests for command parsing, comp selection, and Slack matching."""

from __future__ import annotations

import unittest
from datetime import date

from cma.errors import CmaError
from cma.geo import haversine_miles
from cma.listings import homes_to_comps, parse_region, same_property, street_key
from cma.models import Comp, Subject
from cma.parse import parse_command
from cma.report import render_text
from cma.select import indicate_value, select_comps
from cma.slack_bot import channel_allowed, message_is_cma
from cma.subject import _situs_prefix


class ParseCommandTest(unittest.TestCase):
    def test_address_glued_to_command(self):
        address = parse_command("/cma428 Lawnview Ave, New Castle, Pennsylvania 16105")
        self.assertEqual(address, "428 Lawnview Ave, New Castle, Pennsylvania 16105")

    def test_space_colon_and_mention(self):
        self.assertEqual(parse_command("/cma 428 Lawnview Ave, New Castle, PA 16105"), "428 Lawnview Ave, New Castle, PA 16105")
        self.assertEqual(parse_command("/CMA:428 Lawnview Ave, New Castle, PA 16105"), "428 Lawnview Ave, New Castle, PA 16105")
        self.assertEqual(
            parse_command("<@U123> /cma428 Lawnview Ave, New Castle, PA 16105"),
            "428 Lawnview Ave, New Castle, PA 16105",
        )

    def test_rejects_other_text(self):
        with self.assertRaises(CmaError):
            parse_command("what is the market like")
        with self.assertRaises(CmaError):
            parse_command("/cmap428 Lawnview Ave")
        with self.assertRaises(CmaError):
            parse_command("/cma")


class GeoAndRegionTest(unittest.TestCase):
    def test_one_mile_north(self):
        miles = haversine_miles(41.0, -80.0, 41.0 + 1 / 69.0, -80.0)
        self.assertAlmostEqual(miles, 1.0, delta=0.02)

    def test_region_parser_prefers_named_zip(self):
        html = """
        region_id=16105&region_type=2
        market=pittsburgh&region_id=6062&region_type=2
        "region_id":6062,"region_type":2,"region_name":"16105"
        """
        self.assertEqual(parse_region(html, "16105"), ("6062", "pittsburgh"))

    def test_street_identity(self):
        self.assertEqual(street_key("428 Lawnview Ave, New Castle, PA 16105"), ("428", "lawnview"))
        self.assertTrue(same_property("428 Lawnview Ave, New Castle, Pennsylvania 16105", "428 Lawnview, New Castle, PA 16105"))
        self.assertFalse(same_property("428 Lawnview Ave", "410 Lawnview Ave"))
        self.assertEqual(_situs_prefix("428 Lawnview Ave, New Castle, PA 16105"), "428 Lawnview")
        self.assertEqual(_situs_prefix("123 N Main St"), "123 N Main")


class ListingMapTest(unittest.TestCase):
    def test_maps_closed_home_inside_radius(self):
        home = {
            "mlsStatus": "Closed",
            "price": {"value": 180000, "level": 1},
            "beds": 3,
            "baths": 1.5,
            "sqFt": {"value": 1200, "level": 1},
            "yearBuilt": {"value": 1940, "level": 1},
            "latLong": {"value": {"latitude": 41.0343, "longitude": -80.3356}, "level": 1},
            "streetLine": {"value": "410 Lawnview", "level": 1},
            "city": "New Castle",
            "state": "PA",
            "zip": "16105",
            "soldDate": 1784185200000,
            "url": "/PA/New-Castle/410-Lawnview-Ave-16105/home/1",
            "propertyId": 99,
            "uiPropertyType": 1,
            "dom": {"value": 12, "level": 1},
        }
        comps = homes_to_comps(
            [home],
            group="sold",
            origin_lat=41.03428,
            origin_lng=-80.33561,
            radius_miles=1,
            sold_within_days=365,
            today=date(2026, 9, 29),
        )
        self.assertEqual(len(comps), 1)
        self.assertEqual(comps[0].price, 180000)
        self.assertEqual(comps[0].group, "sold")
        self.assertLess(comps[0].distance_miles, 0.05)
        self.assertTrue(comps[0].url.startswith("https://www.redfin.com/"))

    def test_drops_land_and_far_homes(self):
        land = {
            "mlsStatus": "Active",
            "price": {"value": 29900},
            "beds": 0,
            "latLong": {"value": {"latitude": 41.0343, "longitude": -80.3356}},
            "streetLine": {"value": "82 Blews Way"},
            "city": "New Castle",
            "state": "PA",
            "zip": "16105",
            "uiPropertyType": 5,
            "propertyId": 1,
        }
        far = {
            "mlsStatus": "Active",
            "price": {"value": 150000},
            "beds": 3,
            "sqFt": {"value": 1100},
            "latLong": {"value": {"latitude": 41.2, "longitude": -80.5}},
            "streetLine": {"value": "1 Far Away Rd"},
            "city": "New Castle",
            "state": "PA",
            "zip": "16105",
            "uiPropertyType": 1,
            "propertyId": 2,
        }
        comps = homes_to_comps(
            [land, far],
            group="active",
            origin_lat=41.03428,
            origin_lng=-80.33561,
            radius_miles=1,
            sold_within_days=365,
            today=date(2026, 9, 29),
        )
        self.assertEqual(comps, [])


def _comp(**overrides) -> Comp:
    data = dict(
        address="1 Test St, New Castle, PA 16105",
        group="sold",
        mls_status="Closed",
        price=150000,
        beds=2,
        baths=1,
        sqft=1100,
        year_built=1940,
        distance_miles=0.2,
        sold_date=date(2026, 8, 1),
        dom=None,
        url="https://www.redfin.com/example",
        property_id="1",
        street_number="1",
        street_name="test",
    )
    data.update(overrides)
    return Comp(**data)


class SelectTest(unittest.TestCase):
    def test_mixes_three_sold_and_two_active(self):
        subject = Subject(
            address="428 Lawnview Ave, New Castle, PA 16105",
            matched_address="428 LAWNVIEW AVE",
            latitude=41.03,
            longitude=-80.33,
            zip_code="16105",
            city="NEW CASTLE",
            state="PA",
            beds=2,
            baths=1,
            sqft=1089,
        )
        sold = [
            _comp(property_id=str(i), address=f"{i} Sold St", distance_miles=0.1 * i, price=100000 + i * 1000)
            for i in range(1, 6)
        ]
        active = [
            _comp(
                property_id=f"a{i}",
                group="active",
                mls_status="Active",
                address=f"{i} Active St",
                distance_miles=0.15 * i,
                sold_date=None,
                dom=10,
            )
            for i in range(1, 4)
        ]
        chosen = select_comps(sold, active, subject, today=date(2026, 9, 29))
        self.assertEqual(len(chosen), 5)
        self.assertEqual(sum(comp.group == "sold" for comp in chosen), 3)
        self.assertEqual(sum(comp.group == "active" for comp in chosen), 2)
        self.assertEqual([comp.group for comp in chosen].index("active") > 0, True)

    def test_nearby_sized_home_outranks_farther_unsized_match(self):
        subject = Subject(
            address="428 Lawnview Ave",
            matched_address="428 LAWNVIEW AVE",
            latitude=41.03,
            longitude=-80.33,
            zip_code="16105",
            city="NEW CASTLE",
            state="PA",
            beds=2,
            baths=1,
            sqft=1089,
        )
        nearby = _comp(property_id="near", address="411 Lawnview Ave", distance_miles=0.03, beds=3, sqft=1000, price=180000)
        farther = _comp(property_id="far", address="2722 Old Plank Rd", distance_miles=0.40, beds=2, baths=1, sqft=None, price=125000)
        chosen = select_comps([nearby, farther], [], subject, today=date(2026, 9, 29))
        self.assertEqual(chosen[0].property_id, "near")

    def test_value_band_uses_subject_sqft(self):
        subject = Subject(
            address="428 Lawnview Ave",
            matched_address="428 LAWNVIEW AVE",
            latitude=0,
            longitude=0,
            zip_code="16105",
            city="",
            state="PA",
            sqft=1000,
        )
        comps = [
            _comp(price=100000, sqft=1000),
            _comp(property_id="2", price=150000, sqft=1000),
        ]
        indication = indicate_value(subject, comps)
        self.assertEqual(indication.low, 100000)
        self.assertEqual(indication.high, 150000)
        self.assertEqual(indication.median_price_per_sqft, 125)

    def test_report_lists_both_groups(self):
        subject = Subject(
            address="428 Lawnview Ave, New Castle, Pennsylvania 16105",
            matched_address="428 LAWNVIEW AVE, NEW CASTLE, PA, 16105",
            latitude=41.0,
            longitude=-80.0,
            zip_code="16105",
            city="NEW CASTLE",
            state="PA",
            beds=2,
            baths=1,
            sqft=1089,
            year_built=1939,
            facts_source="the Lawrence County assessment record",
        )
        from cma.models import Indication, Report

        report = Report(
            subject=subject,
            comps=[
                _comp(),
                _comp(property_id="2", group="active", mls_status="Active", address="405 Lawnview Ave, New Castle, PA 16105", sold_date=None, dom=4),
            ],
            pool_sold=8,
            pool_active=6,
            radius_miles=1,
            sold_within_days=365,
            indication=Indication(low=110000, high=160000, median_price_per_sqft=120, basis="sold comps below, applied to the subject square footage"),
        )
        text = render_text(report)
        self.assertIn("*Sold*", text)
        self.assertIn("*On the market*", text)
        self.assertIn("405 Lawnview Ave", text)
        self.assertIn("not an appraisal", text)
        self.assertNotIn("WHITE", text)


class SlackMatchTest(unittest.TestCase):
    def test_message_shapes(self):
        self.assertTrue(message_is_cma("/cma428 Lawnview Ave, New Castle, Pennsylvania 16105"))
        self.assertTrue(message_is_cma("<@U1> /cma 428 Lawnview Ave, New Castle, PA 16105"))
        self.assertFalse(message_is_cma("pull comps for 428 Lawnview"))
        self.assertFalse(message_is_cma("/cmap428 Lawnview"))

    def test_channel_filter(self):
        import os

        os.environ.pop("CMA_SLACK_CHANNEL_ID", None)
        self.assertTrue(channel_allowed("C123"))
        os.environ["CMA_SLACK_CHANNEL_ID"] = "C123"
        try:
            self.assertTrue(channel_allowed("C123"))
            self.assertFalse(channel_allowed("C999"))
        finally:
            os.environ.pop("CMA_SLACK_CHANNEL_ID", None)


if __name__ == "__main__":
    unittest.main()
