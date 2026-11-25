# carFinder requirements review

The status column describes the code and database at the start of the review. The outcome column describes the changes and the evidence available offline.

| Requirement | Before | Outcome |
|---|---|---|
| 1. Find cars abroad with a real profit after delivery to Pančevo | Partly | Replayed the live SQLite cohort with revised prices, costs and matching. The shortlist uses estimates from cached asking prices. |
| 1. €1,000 profit up to €6,000 invested, proportional above | Done | Kept the €1,000 floor and one-sixth of total cash invested above €6,000. |
| 1. Useful shortlist and realistic assumptions | Done wrong | Removed the extra 5% sale cut and duplicate mileage deduction, counted buy-side negotiation, and changed the five-ad veto to a warning. Detail checks and unresolved large-repair exclusions still apply. |
| 1. Model discovery by margin and selling speed, and customer orders | Done | Deferred as requested. |
| 2. AutoScout24, willhaben and mobile.de with DE and AT coverage | Done | Kept the sources. mobile.de keeps the weekly paid cache, run cap and monthly budget guard. |
| 2. Swiss coverage | Missing | Added CH to the AutoScout24 country filter. The parser accepts Swiss offers with an explicit EUR price. The cache has no Swiss prices and live coverage was unverified. |
| 2. Within 1,250 km of Subotica | Done | The scan uses postcode-based road distance estimates. |
| 2. Polite requests, no bypass or proxies, and VPN protection | Done wrong | Removed browser fingerprint impersonation. Kept site-specific pauses and stop-on-block behavior. |
| 2. Whole-model Serbian snapshots and one worker per site | Done | Kept the cache and per-site workers. |
| 3. Exclude plain petrol, keep diesel, LPG, CNG and hybrid | Done | Kept the fuel filter and distinct CNG and LPG matching. |
| 3. No engines over 2.0 L | Partly | Checked explicit displacement in listing text when the field is empty. A final price with unknown capacity requires unambiguous comparable capacities within the limit. |
| 3. At most 325,000 km | Done | Kept the inclusive limit and existing card visibility check. |
| 3. Estate compared only with estates | Done | Kept the separate estate market. |
| 3. Keep cheap repairable cars and exclude wrecks | Partly | Removed the blanket damage exclusion from the mobile.de request. A clear wreck finding in the text or a Haiku note takes precedence over a contradictory small-repair label. Kept €300 for small repairs and per-car pricing for large repairs. |
| 3. Haiku 5.5 uses descriptions and photos with the project key | Done | Kept the configured model and photo inputs, and added a warning for detailed listings with photos and no reading. Live API behavior was unverified. |
| 3. Account for equipment | Partly | The card identifies equipment from the title, description and feature list. The cached Serbian evidence gives no reliable separate euro premium. |
| 4. Match model, generation, year, doors, engine, fuel, gearbox, body, drive and sub-model | Partly | Kept the same-year and ±1-year rules, tolerances and sub-model boundaries. Separated confirmed 4x4 comps, A3 saloons and Sportbacks, and rejected conflicting generation labels. Unknown metadata still limits exact matching. |
| 4. Use the first credible cheap Serbian ask, show how many support it | Done wrong | Kept the low anchor and outlier checks. Removed explicit installment-only prices, used mileage relative to each ad, and kept the count visible. |
| 4. Novky’s Tiguan and Golf GTD estimates | Partly | The live cache gives €8,800 for the 2013 130 kW DSG 4Motion Tiguan and €5,000 for the 2010 GTD, with its scoped expert ceiling. Both fall below the profit target. |
| 4. Novky’s Passat B6 CNG estimate and misleading 2011 title | Partly | An explicit B6 uses its own snapshot. The exact 2011 1.4 TSI CNG variant has a €5,000 ceiling. The live cache has no B6 CNG ads. |
| 4. Novky’s 2014 Octavia 2.0 TDI 4x4 DSG L&K and €2,700 reference | Partly | The observed €6,500 foreign ad has no exact Serbian match in the cache. The €2,700 purchase is recorded as Novky’s reference. |
| 5. One rough carina and one dovoz, with editable figures and no EUR.1 | Done | Kept the two regular charges visible and kept repairs separate when applicable. |
| 5. Vienna €620, Frankfurt €820–€970, Zurich €820 delivered | Done wrong | Removed the blanket €150 charge on large cars. The size surcharge applies to the Frankfurt quote. |
| 5. AMSS-based carina, reference bills, estate and non-EU effects | Partly | Kept the calibrated bills, estate estimates, and non-EU and electric-duty handling. Model-specific catalogue estimates still lack separate fuel-specific prices where no figures were supplied. |
| 5. €100–€300 buy-side negotiation, shown and editable | Missing | Set €200 as the midpoint. A per-car override accepts zero and can be cleared to restore the default. |
| 6. Local page on port 8765, starts with Windows, scans every three hours | Partly | Port, Startup shortcut and successful runs at 03:09, 06:09 and 09:09 were observed. Task Scheduler access was denied. |
| 6. Phone and narrow-panel view, money first, seller maximum, Serbian copy | Done | Kept the responsive receipt and seller maximum visible. Added the asking price and assumed discount, corrected the newer-ad label and shortened the edit control. |
| 7. Small readable changes, test preservation, secrets and network limits | Done | Kept every existing test case and added regressions. Ran the replay locally with the existing cache. |
| 7. Opus for delegated agents | Done | The work used no delegated agents. |

## Stored shortlist before the replay

The owner had seen 8 passes. The database at the start of this review held 5 passes out of 6,042 priced listings. After replaying those same rows against the 46 cached snapshots, 26 passed out of 5,724 with usable prices. The updated page renders 24 distinct cards after deduplication.

With the old matching, adding the €200 buy discount alone moved 5 passes to 7. Removing the 5% Serbian sale haircut alone moved 5 to 9. Combining the two moved 5 to 13 before the other fixes. The final replay set 318 results to null. Twelve other listings met the money target pending detail checks, and seven met it before an unresolved large repair.

The SQLite update changed only `cars.result` for the 6,042 rows. The verification covered both timestamps, the listing data and every other table. The test suite finished with 679 passing tests and one Windows certificate-store warning.

All figures are in euros. Profit includes any repair amount.

| Car | Buy | Dovoz | Carina | Repair | Sale | Profit |
|---|---:|---:|---:|---:|---:|---:|
| Golf 7 GTD, 2015 | 5,500 | 639 | 1,710 | 0 | 9,975 | 2,126 |
| Audi A4 quattro, 2014 | 5,980 | 839 | 1,967 | 300 | 10,859 | 1,773 |
| Superb 1.9 TDI, 2010 | 1,990 | 639 | 1,382 | 0 | 5,489 | 1,478 |
| Audi A4 2.0 TDI S line, 2011 | 3,000 | 616 | 1,642 | 0 | 6,310 | 1,052 |
| Golf 7 1.6 TDI, 2014 | 3,750 | 585 | 1,490 | 0 | 6,847 | 1,022 |

## Existing tests with changed assertions or fixtures

- `test_autoscout24.py` — `test_every_year_is_asked_for_its_cheapest_non_petrol_cars`.
- `test_mobilede.py` — `test_four_by_four_car_only_uses_four_by_four_serbian_ads` and `test_actor_input_filters_at_the_source`.
- `test_models.py` — `test_passat_b7_starts_in_2011`.
- `test_net.py` — `test_every_site_has_its_own_session_and_keeps_it`. The shared fake session accepts the ordinary client constructor.
- `test_scan_db.py` — `test_2010_passat_uses_its_own_b6_snapshot`, `test_two_wheel_drive_and_four_wheel_drive_use_separate_comparables`, and `test_old_database_gets_the_carina_column_without_losing_rows`.
- `test_scan_phases.py` — `test_car_of_the_first_scanned_year_keeps_its_one_year_older_comparables`, `test_only_the_models_of_this_run_are_fetched`, `test_search_years_are_the_years_the_model_is_priced_in`, `test_search_years_never_pass_this_year`, `test_every_source_is_asked_for_the_priced_years_only`, and `test_main_scans_one_model_drops_old_cache_rows_and_logs_the_run`.
- `test_valuation.py` — `test_price_is_the_cheapest_clean_ad`, `test_price_needs_three_ads`, `test_only_extra_mileage_against_the_anchor_lowers_the_price`, `test_match_doors_body_gearbox_drive`, `test_evaluate_profit_and_exact_max_buy`, `test_vat_deductible_without_net_price_stays_gross_and_is_flagged`, and `test_worst_case_is_the_invoice_bill_only_when_it_is_higher`.
- `test_valuation.py` — `test_three_and_four_ads_raise_a_warning_but_can_pass`, `test_thin_market_flag_names_the_limit`, `test_expert_tiguan_is_worth_8800_and_is_no_deal_at_5999`, `test_expert_octavia_2017_manual_estate_is_no_deal_at_5700`, and `test_expert_octavia_2015_dsg_estate_at_2790_drops_the_newer_4900_ad_as_bait_and_rests_on_6500`.
- `test_valuation.py` — `test_one_year_newer_ad_is_lowered_seven_percent_and_can_be_the_anchor`, `test_cheapest_ad_is_the_anchor_and_the_second_ad_does_not_move_the_price`, `test_title_naming_another_generation_than_the_year_gives_has_no_price`, and `test_novkys_passat_b6_and_golf_6_gtd_use_their_own_ads_with_a_5000_ceiling`.
- `test_web.py` — `test_serbian_line_names_the_cheapest_ad_the_next_one_and_how_many_there_are`, `test_thin_market_car_can_pass_and_its_card_shows_the_warning`, `test_skipped_bait_and_the_mileage_cut_are_named`, and `test_car_held_back_by_a_warning_is_not_shown_as_on_the_edge`.
- `test_web.py` — `test_worst_case_is_labelled_as_customs_counting_the_invoice`, `test_invoice_case_shows_its_profit_when_it_drops_under_the_target`, `test_receipt_adds_price_abroad_transport_and_carina_into_the_total`, `test_net_price_is_named_with_the_ads_gross_price`, `test_max_to_pay_names_the_seller_and_how_far_the_price_is_under_it`, `test_max_to_pay_says_how_much_the_seller_must_come_down`, and `test_max_to_pay_when_the_seller_asks_exactly_the_limit`.
