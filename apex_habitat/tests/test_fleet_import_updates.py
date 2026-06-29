# Copyright (c) 2026, AFMCO and contributors
import os
import shutil
import tempfile
import frappe
from frappe.tests.utils import FrappeTestCase
from apex_habitat.salis.fleet_import import run

class TestFleetImportUpdates(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        
        self.created_drivers = []
        self.created_vehicles = []
        self.created_projects = []
        self.created_categories = []
        self.created_offices = []

    def tearDown(self):
        frappe.set_user("Administrator")
        for v in self.created_vehicles:
            if frappe.db.exists("Salis Vehicle", v):
                frappe.delete_doc("Salis Vehicle", v, ignore_permissions=True, force=True)
        for d in self.created_drivers:
            if frappe.db.exists("Salis Driver", d):
                frappe.delete_doc("Salis Driver", d, ignore_permissions=True, force=True)
        for p in self.created_projects:
            if frappe.db.exists("Project", p):
                frappe.delete_doc("Project", p, ignore_permissions=True, force=True)
        for c in self.created_categories:
            if frappe.db.exists("Vehicle Category", c):
                frappe.delete_doc("Vehicle Category", c, ignore_permissions=True, force=True)
        for o in self.created_offices:
            if frappe.db.exists("Rental Office", o):
                frappe.delete_doc("Rental Office", o, ignore_permissions=True, force=True)
        
        frappe.db.commit()
        shutil.rmtree(self.temp_dir)
        super().tearDown()

    def write_csv(self, filename, headers, rows):
        filepath = os.path.join(self.temp_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(",".join(headers) + "\n")
            for row in rows:
                f.write(",".join(str(val) for val in row) + "\n")

    def test_fleet_import_updates(self):
        # 1. Write the initial CSV files
        self.write_csv("project.csv", ["project_name"], [["Import Test Project"]])
        self.write_csv("vehicle_category.csv", ["category_name", "default_fuel_type"], [["Import Test Category", "Petrol"]])
        self.write_csv("rental_office.csv", ["office_name", "status"], [["Import Test Office", "Active"]])
        
        self.write_csv("salis_driver.csv", 
            ["driver_id", "full_name", "phone", "status", "project"],
            [["D-109", "Initial Driver Name", "+123456789", "Active", "Import Test Project"]]
        )
        self.write_csv("salis_vehicle.csv", 
            ["plate_number", "vehicle_category", "ownership", "rental_office", "project", "status"],
            [["ABC 123", "Import Test Category", "Owned", "Import Test Office", "Import Test Project", "Active"]]
        )

        # Run import first time
        run(self.temp_dir)
        
        # Get actual document names from DB
        driver_name = frappe.db.get_value("Salis Driver", {"driver_id": "D-109"}, "name")
        vehicle_name = frappe.db.get_value("Salis Vehicle", {"plate_normalized": "ABC123"}, "name")
        project_name = frappe.db.get_value("Project", {"project_name": "Import Test Project"}, "name")
        
        self.assertTrue(bool(driver_name))
        self.assertTrue(bool(vehicle_name))
        self.assertTrue(bool(project_name))

        # Add to cleanup tracking
        self.created_drivers.append(driver_name)
        self.created_vehicles.append(vehicle_name)
        self.created_projects.append(project_name)
        self.created_categories.append("Import Test Category")
        self.created_offices.append("Import Test Office")

        # Verify initial values
        driver = frappe.get_doc("Salis Driver", driver_name)
        self.assertEqual(driver.full_name, "Initial Driver Name")
        self.assertEqual(driver.phone, "+123456789")
        self.assertEqual(driver.status, "Active")

        vehicle = frappe.get_doc("Salis Vehicle", vehicle_name)
        self.assertEqual(vehicle.plate_number, "ABC 123")
        self.assertEqual(vehicle.ownership, "Owned")
        self.assertEqual(vehicle.status, "Active")

        # 2. Write CSV files with updated values for existing records
        self.write_csv("salis_driver.csv", 
            ["driver_id", "full_name", "phone", "status", "project"],
            [["D-109", "Updated Driver Name", "+987654321", "Stopped", "Import Test Project"]]
        )
        self.write_csv("salis_vehicle.csv", 
            ["plate_number", "vehicle_category", "ownership", "rental_office", "project", "status"],
            [["ABC 123", "Import Test Category", "Rented", "Import Test Office", "Import Test Project", "Stopped"]]
        )

        # Run import second time
        run(self.temp_dir)

        # Fetch and verify updated values
        driver.reload()
        self.assertEqual(driver.full_name, "Updated Driver Name")
        self.assertEqual(driver.phone, "+987654321")
        self.assertEqual(driver.status, "Stopped")

        vehicle.reload()
        self.assertEqual(vehicle.ownership, "Rented")
        self.assertEqual(vehicle.status, "Stopped")
