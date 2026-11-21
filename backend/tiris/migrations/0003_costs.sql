-- Costs: meters, readings, tariffs, installment plans, payments.
CREATE TABLE meters (
    id              BIGSERIAL PRIMARY KEY,
    kind            TEXT NOT NULL CHECK (kind IN ('electricity', 'gas')),
    name            TEXT NOT NULL,
    number          TEXT,                        -- meter number from the bill
    unit            TEXT NOT NULL DEFAULT 'kWh', -- kWh, or m3 for gas meters
    -- gas: kWh = m3 x calorific value x z-number (both from the gas bill)
    calorific_value NUMERIC(6,3),
    z_number        NUMERIC(6,4),
    archived        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE meter_readings (
    meter_id   BIGINT NOT NULL REFERENCES meters(id) ON DELETE CASCADE,
    day        DATE NOT NULL,
    value      NUMERIC(14,3) NOT NULL,           -- in the meter's unit
    estimated  BOOLEAN NOT NULL DEFAULT FALSE,   -- estimate by the supplier instead of a reading
    note       TEXT,
    PRIMARY KEY (meter_id, day)
);

CREATE TABLE tariffs (
    id                 BIGSERIAL PRIMARY KEY,
    meter_id           BIGINT NOT NULL REFERENCES meters(id) ON DELETE CASCADE,
    valid_from         DATE NOT NULL,
    valid_to           DATE,                     -- inclusive; NULL = open
    provider           TEXT,
    name               TEXT,
    energy_ct_net      NUMERIC(8,4) NOT NULL,    -- energy price, ct per kWh, net
    base_eur_year_net  NUMERIC(9,2) NOT NULL,    -- base price per year, net
    vat_pct            NUMERIC(5,2) NOT NULL DEFAULT 19,
    contract_end       DATE,
    UNIQUE (meter_id, valid_from)
);

-- What the supplier debits each month, with validity ("Abschlag von ... bis ...").
CREATE TABLE installment_plans (
    id            BIGSERIAL PRIMARY KEY,
    meter_id      BIGINT NOT NULL REFERENCES meters(id) ON DELETE CASCADE,
    valid_from    DATE NOT NULL,                 -- first due date
    valid_to      DATE,                          -- last due date, inclusive; NULL = open
    amount_gross  NUMERIC(9,2) NOT NULL,
    note          TEXT
);

-- Bank movements for a meter's contract. Positive = paid, negative = refund.
CREATE TABLE payments (
    id            BIGSERIAL PRIMARY KEY,
    meter_id      BIGINT REFERENCES meters(id) ON DELETE SET NULL,   -- NULL = not assigned yet
    day           DATE NOT NULL,
    amount        NUMERIC(10,2) NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'installment' CHECK (kind IN ('installment', 'settlement', 'other')),
    note          TEXT,
    external_ref  TEXT,                          -- e.g. bank transaction id, for de-duplication on import
    UNIQUE (external_ref)
);
CREATE INDEX ON payments (meter_id, day);
