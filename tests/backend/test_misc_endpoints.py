"""
Tests for miscellaneous API endpoints (demand, backlog, spending).
"""
import pytest


class TestDemandEndpoints:
    """Test suite for demand forecast endpoints."""

    def test_get_demand_forecasts(self, client):
        """Test getting demand forecasts."""
        response = client.get("/api/demand")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

        # Check structure if data exists
        if len(data) > 0:
            forecast = data[0]
            assert "id" in forecast
            assert "item_sku" in forecast
            assert "item_name" in forecast
            assert "current_demand" in forecast
            assert "forecasted_demand" in forecast
            assert "trend" in forecast
            assert "period" in forecast

    def test_demand_forecast_trends(self, client):
        """Test that demand forecasts have valid trend values."""
        response = client.get("/api/demand")
        data = response.json()

        valid_trends = ["increasing", "stable", "decreasing"]

        for forecast in data:
            assert forecast["trend"].lower() in valid_trends

    def test_demand_forecast_values(self, client):
        """Test that demand forecast values are non-negative."""
        response = client.get("/api/demand")
        data = response.json()

        for forecast in data:
            assert forecast["current_demand"] >= 0
            assert forecast["forecasted_demand"] >= 0

    def test_stable_demand_items_have_small_changes(self, client):
        """Test that items with 'stable' trend have less than 2% change."""
        response = client.get("/api/demand")
        data = response.json()

        stable_items = [item for item in data if item["trend"].lower() == "stable"]

        # Should have at least 5 stable items
        assert len(stable_items) >= 5, f"Expected at least 5 stable items, found {len(stable_items)}"

        for item in stable_items:
            current = item["current_demand"]
            forecasted = item["forecasted_demand"]

            # Calculate percentage change
            if current > 0:
                percent_change = abs((forecasted - current) / current) * 100
                assert percent_change < 2.0, \
                    f"Item {item['item_name']} has {percent_change:.2f}% change, expected < 2%"

    def test_every_forecast_sku_exists_in_inventory(self, client):
        """Test that every forecast SKU joins to a real inventory item.

        This replaces an older test that asserted the presence of SNR-420 and
        CTL-330. Those SKUs were part of a legacy catalog that no longer exists in
        inventory.json, so the old test was pinning a broken join in place: only 1
        of the 9 forecasts could be matched to an item, which left any feature
        needing both demand and cost data with almost no rows to work with.
        """
        forecasts = client.get("/api/demand").json()
        inventory_skus = {item["sku"] for item in client.get("/api/inventory").json()}

        orphans = [f["item_sku"] for f in forecasts if f["item_sku"] not in inventory_skus]
        assert not orphans, f"Forecast SKUs missing from inventory: {', '.join(orphans)}"

    def test_forecast_names_match_inventory_names(self, client):
        """Test that forecast item names agree with their inventory records.

        The Japanese locale translates product names by exact string lookup, so a
        forecast name that drifts from its inventory name silently falls back to
        English on the Demand and Restocking tabs.
        """
        forecasts = client.get("/api/demand").json()
        inventory_names = {item["sku"]: item["name"] for item in client.get("/api/inventory").json()}

        for forecast in forecasts:
            expected = inventory_names.get(forecast["item_sku"])
            assert forecast["item_name"] == expected, \
                f"{forecast['item_sku']}: forecast name '{forecast['item_name']}' != inventory name '{expected}'"

    def test_demand_forecast_covers_all_trends(self, client):
        """Test that the forecast set spans every trend, so trend-driven UI has data."""
        trends = {item["trend"].lower() for item in client.get("/api/demand").json()}
        assert {"increasing", "stable", "decreasing"} <= trends, \
            f"Expected all three trends to be represented, found {trends}"


class TestBacklogEndpoints:
    """Test suite for backlog endpoints."""

    def test_get_backlog(self, client):
        """Test getting backlog items."""
        response = client.get("/api/backlog")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

        # Check structure if data exists
        if len(data) > 0:
            backlog_item = data[0]
            assert "id" in backlog_item
            assert "order_id" in backlog_item
            assert "item_sku" in backlog_item
            assert "item_name" in backlog_item
            assert "quantity_needed" in backlog_item
            assert "quantity_available" in backlog_item
            assert "days_delayed" in backlog_item
            assert "priority" in backlog_item

    def test_backlog_priority_values(self, client):
        """Test that backlog items have valid priority values."""
        response = client.get("/api/backlog")
        data = response.json()

        valid_priorities = ["high", "medium", "low"]

        for item in data:
            assert item["priority"].lower() in valid_priorities

    def test_backlog_quantity_logic(self, client):
        """Test that backlog quantities are non-negative."""
        response = client.get("/api/backlog")
        data = response.json()

        for item in data:
            # Quantities should be non-negative
            assert item["quantity_needed"] >= 0
            assert item["quantity_available"] >= 0

    def test_backlog_days_delayed(self, client):
        """Test that days delayed is non-negative."""
        response = client.get("/api/backlog")
        data = response.json()

        for item in data:
            assert item["days_delayed"] >= 0


class TestSpendingEndpoints:
    """Test suite for spending-related endpoints."""

    def test_get_spending_summary(self, client):
        """Test getting spending summary."""
        response = client.get("/api/spending/summary")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, dict)

    def test_get_monthly_spending(self, client):
        """Test getting monthly spending data."""
        response = client.get("/api/spending/monthly")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

        # Check structure if data exists
        if len(data) > 0:
            month_data = data[0]
            assert "month" in month_data or "period" in month_data

    def test_monthly_spending_has_all_cost_categories(self, client):
        """Test that monthly spending includes all cost categories."""
        response = client.get("/api/spending/monthly")
        data = response.json()

        required_fields = ["procurement", "operational", "labor", "overhead"]

        for month_data in data:
            for field in required_fields:
                assert field in month_data, f"Missing {field} in monthly spending"
                assert isinstance(month_data[field], (int, float))
                assert month_data[field] >= 0

    def test_monthly_spending_has_variety(self, client):
        """Test that monthly spending data has variety (not all the same)."""
        response = client.get("/api/spending/monthly")
        data = response.json()

        # Collect all procurement values
        procurement_values = [month["procurement"] for month in data]

        # Should have at least 3 different values (variety)
        unique_values = set(procurement_values)
        assert len(unique_values) >= 3, \
            "Monthly spending should have variety, not all the same values"

        # Same for other categories
        operational_values = set(month["operational"] for month in data)
        assert len(operational_values) >= 3, \
            "Operational costs should have variety across months"

    def test_get_category_spending(self, client):
        """Test getting spending by category."""
        response = client.get("/api/spending/categories")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

        # Check structure if data exists
        if len(data) > 0:
            category_data = data[0]
            assert "category" in category_data or "name" in category_data

    def test_get_recent_transactions(self, client):
        """Test getting recent transactions."""
        response = client.get("/api/spending/transactions")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

        # Check structure if data exists
        if len(data) > 0:
            transaction = data[0]
            # Transactions should have some identifying fields
            assert isinstance(transaction, dict)


class TestRootEndpoint:
    """Test suite for root endpoint."""

    def test_root_endpoint(self, client):
        """Test the root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, dict)
        assert "message" in data or "version" in data

    def test_root_endpoint_structure(self, client):
        """Test root endpoint has expected structure."""
        response = client.get("/")
        data = response.json()

        # Should have message and version
        assert "message" in data
        assert "version" in data
        assert isinstance(data["message"], str)
        assert isinstance(data["version"], str)
