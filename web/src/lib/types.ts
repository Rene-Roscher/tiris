/** Response shapes of the tiris API (backend: tiris/overview.py, api/*.py). Energy in Wh, power in W. */

export interface DailyRow { day: string; by: Record<string, number>; total: number }
export interface MonthRow { month: string; wh: number; partial: boolean; by?: Record<string, number> }
export interface HeatCell { dow: number; hour: number; wh: number; n: number }

export interface OverviewDevice {
  id: string; name: string; model: string; ip: string | null; last_seen: string | null; slot: number
  range_wh: number; last30_wh: number; mtd_wh: number; today_wh: number; spark: number[]; base_w: number | null
}

export interface Overview {
  now: string
  price: number | null
  last_run: { at: string; status: 'ok' | 'partial' | 'failed' } | null
  selected: string | null
  range: { start: string; end: string; days: number; all?: boolean; partial_before?: { until: string; from: string; wh: number } | null }
  kpi: {
    today_wh: number; yesterday_same_time_wh: number | null; yesterday_wh: number
    last7_wh: number; prev7_wh: number; last30_wh: number
    mtd_wh: number; mtd_complete_wh: number; prev_month_same_wh: number | null; prev_month_wh: number
    forecast_month_wh: number; forecast_year_wh: number; base_w: number | null; days_in_month: number
    range_wh: number; peak_day: DailyRow | null; peak_month?: MonthRow | null
  }
  daily: DailyRow[]
  series_keys: string[]
  months: MonthRow[]
  heat: HeatCell[]
  heat_days: number
  devices: OverviewDevice[]
}

export interface LiveDevice { w: number; v: number; a: number; pf: number | null; energy_mwh: number; age: number }
export interface LiveSnapshot {
  enabled?: boolean; at: number; total_w: number; online: number; known: number; interval_s: number
  devices: Record<string, LiveDevice>
}
export interface LiveRecent { interval_s: number; total: [number, number][]; devices: Record<string, [number, number][]> }

export interface SeriesResponse {
  bucket: '1m' | '15m' | '1h'; step_s: number; columns: string[]
  points: [number, number, number, number, number | null, number, number][]   // t, w, w_min, w_max, v, wh, n
}

export interface DeviceStatus {
  reachable: boolean; stale?: boolean; error?: string; device_on?: boolean; rssi?: number; signal_level?: number
  on_time_s?: number; fw_ver?: string; hw_ver?: string; overcurrent?: string | null; overheat?: string | null
  power_protection?: string | null; default_state?: string | null
  timer?: { remaining_s: number; delay_s: number; on: boolean } | null
}
export interface Firmware { available?: boolean; version?: string; release_date?: string; notes?: string; error?: string; pending?: boolean }
export interface Device {
  id: string; name: string; model: string; ip: string | null; mac: string | null; hw_ver: string | null
  first_seen: string | null; last_seen: string | null; retired: boolean
  room: string | null; category: string | null; note: string | null; protected: boolean
  /** colour slot 1..6 (top consumers of the last 90 days), 0 = other */
  slot: number
  status: DeviceStatus; firmware: Firmware | null
}
export interface ScheduleRule {
  id: string; enabled: boolean; kind: 'clock' | 'sunrise' | 'sunset'; on: boolean; days: number | null
  hour?: number; minute?: number; offset_minutes?: number
}

export interface Meter {
  id: number; kind: 'electricity' | 'gas'; name: string; number: string | null; unit: 'kWh' | 'm3'
  calorific_value: number | null; z_number: number | null; archived: boolean
}
export interface TariffRow {
  id: number; valid_from: string; valid_to: string | null; provider: string | null; name: string | null
  energy_ct_net: number; base_eur_year_net: number; vat_pct: number; contract_end: string | null
  energy_ct_gross: number; base_eur_month_gross: number
}
export interface Interval {
  from: string; to: string; days: number; kwh: number; kwh_day: number; estimated: boolean
  plugs_kwh: number | null; coverage: number | null; plugs_exact: boolean
}
export interface Billing {
  start: string; end: string; elapsed_days: number; total_days: number; kwh_so_far: number; kwh_so_far_measured: boolean
  kwh_forecast: number; cost_forecast: number; installments_total: number; installments_paid: number
  installments_count: number; paid_source: 'plan' | 'payments'; balance: number; fair_installment: number | null
  tariff_assumed: boolean
}
export interface CostMonth {
  month: string; plugs_kwh: number; plugs_eur: number; rest_kwh: number | null; rest_eur: number | null
  base_eur: number; complete: boolean; partial: boolean
}
export interface DeviceCost { id: string; name: string; kwh_year: number; eur_year: number; eur_month: number; standby_w: number | null; standby_eur_year: number }
export interface MeterCosts {
  meter: Meter & { kwh_per_unit: number }
  tariffs: TariffRow[]
  readings: { day: string; value: number; estimated: boolean; note: string | null }[]
  plans: { id: number; valid_from: string; valid_to: string | null; amount_gross: number; note: string | null }[]
  payments: Payment[]
  price_eur_kwh: number | null; base_eur_month: number | null; contract_end: string | null; warnings: string[]
  intervals: Interval[]
  plugs_kwh_day: number | null; rest_kwh_day: number | null; house_kwh_day: number | null; house_kwh_year: number | null
  plugs_share: number | null
  billing?: Billing
  months?: CostMonth[]
  devices?: DeviceCost[]
}
export interface Payment {
  id: number; meter_id?: number | null; day: string; amount: number; kind: 'installment' | 'settlement' | 'other'
  note: string | null; external_ref: string | null
}
export interface PaymentsResponse { payments: Payment[]; by_year: ({ year: number; total: number } & Record<string, number>)[] }

export interface Run { id: number; started_at: string; finished_at: string | null; status: string | null; ok: number | null; failed: number | null; message: string | null }
