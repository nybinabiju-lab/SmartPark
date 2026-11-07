// Sample parking spots
let parkingSpots = [
  { id: 1, status: "Available" },
  { id: 2, status: "Available" },
  { id: 3, status: "Available" },
  { id: 4, status: "Occupied" }
];

// Reserve a parking spot
function reserveSpot(id) {
  const spot = parkingSpots.find(s => s.id === id);

  if (!spot || spot.status !== "Available") {
    alert("This spot is not available!");
    return;
  }

  spot.status = "Reserved";

  updateAvailableCount();

  alert("Parking spot reserved successfully!");
}

// Update available-space counter
function updateAvailableCount() {
  const available = parkingSpots.filter(
    spot => spot.status === "Available"
  ).length;

  document.getElementById("availableCount").textContent =
    available;
}

// Show the initial count
updateAvailableCount();