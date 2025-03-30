const IOBROKER = true;
const debug = true;

// Define ioBroker states for Tibber prices and solar forecast
const todayPricesState = "tibberlink.0.Homes.<home-id>.PricesToday.json";
const tomorrowPricesState = "tibberlink.0.Homes.<home-id>.PricesTomorrow.json";
const solarForecastState = "pvforecast.0.plants.pv.JSONTable";

const BATTERY_CHARACTERISTICS = {
    capacity: 1900, // Battery capacity in Wh
    maxChargeRate: 1200, // Maximum charge rate in W
    maxDischargeRate: 800 // Maximum discharge rate in W
};

function lg(message, onlyDebug) {
    if (onlyDebug && !debug) { return; }
    if (IOBROKER) { log(message, (onlyDebug ? 'debug' : 'info')); }
    else { console.log(message); }
}

function calculateAdjustedPrice(price, solarPower) {
    // Adjust the Tibber price based on solar production
    let adjustedTotal;

    var remainingSolarPower = Math.max(solarPower - BATTERY_CHARACTERISTICS.maxDischargeRate, 0);
    lg(`${remainingSolarPower} = Math.max(${solarPower} - ${BATTERY_CHARACTERISTICS.maxDischargeRate}, 0)`, true);


    if (remainingSolarPower >= BATTERY_CHARACTERISTICS.maxChargeRate) {
        adjustedTotal = 0; // Solar power exceeds threshold, price is 0
    } else {
        adjustedTotal = price * (1 - remainingSolarPower / BATTERY_CHARACTERISTICS.maxChargeRate); // Reduce proportionally
    }


    return adjustedTotal;
}

function calculatePriceTable(todayPricesState, tomorrowPricesState, solarForecastState) {
    // Read Tibber prices and solar forecast from ioBroker states
    const todayPrices = JSON.parse(getState(todayPricesState).val || "[]");
    const tomorrowPrices = JSON.parse(getState(tomorrowPricesState).val || "[]");
    const solarForecast = JSON.parse(getState(solarForecastState).val || "[]");

    // Combine Tibber prices (all available data)
    const allPrices = [...todayPrices, ...tomorrowPrices];

    // If no Tibber data is available, return an empty table
    if (allPrices.length === 0) {
        log("No Tibber data available. Table cannot be generated.");
        return [];
    }

    // Create the table by aligning Tibber prices with solar production
    const table = allPrices.map((entry, index) => {
        const entryDate = new Date(entry.startsAt);
        const entryHour = entryDate.getHours();

        // Find corresponding solar power data
        const solarEntry = solarForecast.find(solar => {
            const solarDate = new Date(solar.Time);
            return (
                solarDate.getHours() === entryHour &&
                solarDate.toISOString().split('T')[0] === entryDate.toISOString().split('T')[0]
            );
        });

        let solarPower = solarEntry ? parseFloat(solarEntry.Power.replace(/\./g, '').replace(',', '.')) || 0.0 : 0.0;

        // Adjust the Tibber price based on solar production
        let adjustedTotal = calculateAdjustedPrice(entry.total, solarPower);

        // Construct the row
        const row = {
            index: index,
            hour: entryHour,
            date: entryDate.toISOString().split('T')[0],
            tibberTotal: entry.total.toFixed(4),
            solarProduction: solarPower.toFixed(2),
            adjustedPrice: adjustedTotal.toFixed(4)
        };

        // If hour=0, shift the date by 1 day
        if (row.hour === 0) {
            const d = new Date(row.date + "T00:00:00Z");
            d.setDate(d.getDate() + 1);
            row.date = d.toISOString().split("T")[0];
        }

        return row;
    });

    return table;
}

Calculate();
schedule({ minute: [5] }, Calculate);


function Calculate() {
    // Define ioBroker state for the output
    const outputState = "0_userdata.0.tibber_adjusted_prices";

    // Calculate the price table
    const priceTable = calculatePriceTable(todayPricesState, tomorrowPricesState, solarForecastState);
    // Wrap the array in an object, e.g. { data: [...] }
    const wrappedOutput = { data: priceTable };
    setState(outputState, JSON.stringify(wrappedOutput), true);
}
