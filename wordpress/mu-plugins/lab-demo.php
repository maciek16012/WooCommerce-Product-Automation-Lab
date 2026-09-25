<?php
/** Plugin Name: Biurko Lab — local demo guardrails */
// This portfolio environment must never send customer emails.
add_filter('pre_wp_mail', '__return_true');
// Disable third-party marketing recommendations, tracking and marketplace suggestions.
add_filter('woocommerce_allow_marketplace_suggestions','__return_false');
add_filter('woocommerce_admin_features',function($features){return array_values(array_diff($features,['marketing','remote-inbox-notifications','remote-free-extensions']));});
