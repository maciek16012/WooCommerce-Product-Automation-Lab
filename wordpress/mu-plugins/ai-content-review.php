<?php
/**
 * Plugin Name: Lab AI Content Review
 * Description: Server-side wp-admin proxy to the internal Stage 3 review service.
 * Version: 1.3.0
 */
defined('ABSPATH') || exit;

function lab_air_sku($value) {
    return is_string($value) && preg_match('/\A[A-Za-z0-9][A-Za-z0-9._-]{0,79}\z/D', $value);
}

function lab_air_error($code = 'unavailable') {
    $messages = [
        'unauthorized' => 'Backend authentication is unavailable. Check the private server configuration.',
        'bad_request' => 'Invalid request. Reload the product and try again.',
        'not_found' => 'No proposal is available. Select a product and generate one.',
        'conflict' => 'The proposal is unreviewed, stale, changed or busy. Reload and review or regenerate it.',
        'source_invalid' => 'Catalog validation failed. Check the local source and media manifest.',
        'provider_failed' => 'The AI provider is unavailable, unconfigured or returned invalid content. Check local configuration before retrying.',
        'woo_failed' => 'WooCommerce reported an error. Some APPLY writes may already have succeeded. Inspect the local report and run PLAN again.',
        'unavailable' => 'AI Review backend unavailable. Check that the internal service and its private configuration are ready.',
    ];
    return new WP_Error('lab_air_' . $code, $messages[$code] ?? $messages['unavailable']);
}

function lab_air_valid_content($value) {
    if (!is_array($value)) return false;
    foreach (['description', 'short_description', 'image_alt'] as $field) {
        if (!isset($value[$field]) || !is_string($value[$field]) || strlen($value[$field]) > 120000) return false;
    }
    return true;
}

function lab_air_valid_response($endpoint, $data) {
    if (!is_array($data)) return false;
    if ($endpoint === '/products') {
        if (!isset($data['products']) || !is_array($data['products'])) return false;
        foreach ($data['products'] as $row) {
            if (!is_array($row) || !lab_air_sku($row['sku'] ?? null) || !is_string($row['name'] ?? null) || !lab_air_valid_content($row)) return false;
        }
        return true;
    }
    if (in_array($endpoint, ['/plan', '/apply'], true)) {
        if (($data['mode'] ?? '') !== ($endpoint === '/plan' ? 'PLAN' : 'APPLIED')
            || !is_string($data['proposal_id'] ?? null)
            || !preg_match('/\A[a-f0-9]{32}\z/', $data['proposal_id'])
            || !is_array($data['counts'] ?? null) || !is_array($data['requests'] ?? null)
            || !is_array($data['operations'] ?? null)) return false;
        foreach (['CREATE', 'UPDATE', 'SKIP', 'ERROR'] as $key) {
            if (!is_int($data['counts'][$key] ?? null) || $data['counts'][$key] < 0) return false;
        }
        foreach (['GET', 'POST', 'PUT'] as $key) {
            if (!is_int($data['requests'][$key] ?? null) || $data['requests'][$key] < 0) return false;
        }
        foreach ($data['operations'] as $operation) {
            if (!is_array($operation) || !is_string($operation['sku'] ?? null)
                || !in_array($operation['action'] ?? '', ['CREATE','UPDATE','SKIP','ERROR'], true)
                || !is_array($operation['changes'] ?? null)) return false;
            foreach ($operation['changes'] as $change) {
                if (!is_array($change) || !array_key_exists('before', $change) || !array_key_exists('after', $change)) return false;
            }
        }
        return true;
    }
    if (!is_bool($data['exists'] ?? null) || !lab_air_sku($data['sku'] ?? null) || !lab_air_valid_content($data['current'] ?? null)) return false;
    if (!$data['exists']) return true;
    return is_string($data['proposal_id'] ?? null)
        && preg_match('/\A[a-f0-9]{32}\z/', $data['proposal_id'])
        && is_string($data['created_at'] ?? null)
        && in_array($data['approval'] ?? '', ['pending','approved','rejected'], true)
        && lab_air_valid_content($data['proposed'] ?? null)
        && is_array($data['review'] ?? null)
        && is_string($data['review']['decision'] ?? null)
        && is_string($data['review']['reviewed_at'] ?? null);
}

function lab_air_request($endpoint, $body = null) {
    if (!current_user_can('manage_woocommerce') || !class_exists('WooCommerce')) return lab_air_error();
    // This GUI never accepts a URL from a browser. Pin the environment setting too.
    $base = rtrim(getenv('AI_REVIEW_SERVICE_URL') ?: 'http://ai-review:8081', '/');
    $token = getenv('AI_REVIEW_TOKEN');
    if ($base !== 'http://ai-review:8081' || !is_string($token) || !preg_match('/\A[\x21-\x7e]+\z/', $token)) return lab_air_error('unauthorized');
    $path = wp_parse_url($endpoint, PHP_URL_PATH);
    if (!in_array($path, ['/products','/proposal','/propose','/review','/plan','/apply'], true)) return lab_air_error('bad_request');
    $args = [
        'timeout' => $path === '/propose' ? 200 : (in_array($path, ['/plan','/apply'], true) ? 120 : 20),
        'redirection' => 0,
        'limit_response_size' => 2 * 1024 * 1024,
        'headers' => ['X-Lab-Token' => $token, 'Accept' => 'application/json'],
    ];
    if ($body !== null) {
        $args['headers']['Content-Type'] = 'application/json';
        $args['body'] = wp_json_encode($body);
        $response = wp_remote_post($base . $endpoint, $args);
    } else {
        $response = wp_remote_get($base . $endpoint, $args);
    }
    if (is_wp_error($response)) return lab_air_error();
    $status = wp_remote_retrieve_response_code($response);
    $data = json_decode(wp_remote_retrieve_body($response), true);
    // A failed sync may return a safe structured partial-run report.
    if ($status === 502 && in_array($path, ['/plan','/apply'], true)
        && lab_air_valid_response($path, $data) && $data['counts']['ERROR'] > 0) return $data;
    if ($status !== 200) return lab_air_error(is_array($data) && is_string($data['error'] ?? null) ? $data['error'] : 'unavailable');
    return lab_air_valid_response($path, $data) ? $data : lab_air_error();
}

function lab_air_url($sku = '') {
    return add_query_arg(['page' => 'lab-ai-review', 'sku' => $sku], admin_url('admin.php'));
}

function lab_air_cache_key($sku) {
    return 'lab_air_plan_' . get_current_user_id() . '_' . hash('sha256', strtolower($sku));
}

function lab_air_nonce_action($action, $id = '') {
    return 'lab_air_' . $action . ($action === 'apply' ? '_' . $id : '');
}

function lab_air_action() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !current_user_can('manage_woocommerce') || !class_exists('WooCommerce')) {
        wp_die(esc_html__('You are not allowed to perform this action.'), '', ['response' => 403]);
    }
    $action = isset($_POST['lab_action']) && is_string($_POST['lab_action']) ? sanitize_key(wp_unslash($_POST['lab_action'])) : '';
    $sku = isset($_POST['sku']) && is_string($_POST['sku']) ? sanitize_text_field(wp_unslash($_POST['sku'])) : '';
    $id = isset($_POST['proposal_id']) && is_string($_POST['proposal_id']) ? sanitize_text_field(wp_unslash($_POST['proposal_id'])) : '';
    if (!in_array($action, ['propose','approve','reject','plan','apply'], true) || !lab_air_sku($sku)
        || ($action !== 'propose' && !preg_match('/\A[a-f0-9]{32}\z/', $id))) {
        wp_die('Invalid review action.', '', ['response' => 400]);
    }
    check_admin_referer(lab_air_nonce_action($action, $id));
    $body = ['sku' => $sku];
    $endpoint = '/' . $action;
    if ($action === 'propose') {
        $provider = isset($_POST['provider']) && is_string($_POST['provider']) ? sanitize_key(wp_unslash($_POST['provider'])) : '';
        if (!in_array($provider, ['demo','llamacpp','openai'], true)) wp_die('Invalid provider.', '', ['response' => 400]);
        $body['provider'] = $provider;
        update_user_meta(get_current_user_id(), 'lab_air_provider', $provider);
    } else $body['proposal_id'] = $id;
    if ($action === 'approve' || $action === 'reject') {
        $endpoint = '/review';
        $body['decision'] = $action === 'approve' ? 'approved' : 'rejected';
    }
    if ($action === 'apply') {
        $previous = get_transient(lab_air_cache_key($sku));
        if (!is_array($previous) || ($previous['proposal_id'] ?? '') !== $id || ($previous['counts']['ERROR'] ?? 1) !== 0) {
            wp_die('Run and review a successful PLAN before applying.', '', ['response' => 409]);
        }
    }
    delete_transient(lab_air_cache_key($sku));
    $result = lab_air_request($endpoint, $body);
    if ($action === 'plan' && !is_wp_error($result) && $result['counts']['ERROR'] === 0) {
        set_transient(lab_air_cache_key($sku), $result, 10 * MINUTE_IN_SECONDS);
    }
    $flash = ['action' => $action, 'error' => is_wp_error($result) ? $result->get_error_message() : '',
              'run' => !is_wp_error($result) && in_array($action, ['plan','apply'], true) ? $result : null];
    $flash_id = wp_generate_password(24, false, false);
    set_transient('lab_air_flash_' . get_current_user_id() . '_' . $flash_id, $flash, 2 * MINUTE_IN_SECONDS);
    // PRG avoids repeating writes when refreshing the page. No response bodies in URLs.
    wp_safe_redirect(add_query_arg('review_notice', $flash_id, lab_air_url($sku)));
    exit;
}
add_action('admin_post_lab_ai_review', 'lab_air_action');

add_action('admin_menu', function () {
    add_submenu_page('woocommerce', 'AI Content Review', 'AI Content Review', 'manage_woocommerce', 'lab-ai-review', 'lab_air_page');
});

add_action('admin_enqueue_scripts', function ($hook) {
    if ($hook !== 'woocommerce_page_lab-ai-review' || !current_user_can('manage_woocommerce')) return;
    wp_enqueue_style('lab-ai-review', plugins_url('ai-review/admin.css', __FILE__), [], '1.3.0');
    wp_enqueue_script('lab-ai-review', plugins_url('ai-review/admin.js', __FILE__), [], '1.3.0', true);
});

function lab_air_form_start($action, $sku, $id = '', $class = '') {
    echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '" class="lab-air-action ' . esc_attr($class) . '">';
    echo '<input type="hidden" name="action" value="lab_ai_review"><input type="hidden" name="lab_action" value="' . esc_attr($action) . '">';
    echo '<input type="hidden" name="sku" value="' . esc_attr($sku) . '"><input type="hidden" name="proposal_id" value="' . esc_attr($id) . '">';
    wp_nonce_field(lab_air_nonce_action($action, $id));
}

function lab_air_button($action, $label, $sku, $id, $primary = false) {
    lab_air_form_start($action, $sku, $id);
    echo '<button class="button ' . ($primary ? 'button-primary' : '') . '" type="submit">' . esc_html($label) . '</button></form>';
}

function lab_air_badge($label) {
    echo '<span class="air-badge air-' . esc_attr(strtolower($label)) . '">' . esc_html(strtoupper($label)) . '</span>';
}

function lab_air_counts($run) {
    echo '<div class="air-counts">';
    foreach (['CREATE','UPDATE','SKIP','ERROR'] as $key) {
        echo '<div><span>' . esc_html($key) . '</span><strong>' . esc_html((string) $run['counts'][$key]) . '</strong></div>';
    }
    echo '</div>';
}

function lab_air_print_value($value) {
    return is_string($value) ? $value : wp_json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
}

function lab_air_page() {
    if (!current_user_can('manage_woocommerce')) wp_die('Access denied.', '', ['response' => 403]);
    echo '<div class="wrap lab-air"><header class="air-header"><div><span class="air-eyebrow">BIURKO / LAB · AUTOMATION</span><h1>AI Content Review</h1><p>Human-in-the-loop product content workflow</p></div><span class="air-version">STAGE 4 <b>v1.3.0</b></span></header>';
    if (!class_exists('WooCommerce')) {
        echo '<div class="notice notice-warning"><p>Activate WooCommerce to use AI Content Review.</p></div></div>';
        return;
    }
    $response = lab_air_request('/products');
    $connected = !is_wp_error($response);
    $products = $connected ? $response['products'] : [];
    $sku = isset($_GET['sku']) && is_string($_GET['sku']) ? sanitize_text_field(wp_unslash($_GET['sku'])) : ($products[0]['sku'] ?? '');
    $product = null;
    foreach ($products as $row) if (strcasecmp($row['sku'], $sku) === 0) { $product = $row; $sku = $row['sku']; break; }
    $proposal = $product ? lab_air_request('/proposal?sku=' . rawurlencode($sku)) : null;
    $exists = is_array($proposal) && $proposal['exists'];
    $id = $exists ? $proposal['proposal_id'] : '';
    $approval = $exists ? $proposal['approval'] : '';
    $provider = get_user_meta(get_current_user_id(), 'lab_air_provider', true);
    $providers = ['llamacpp' => 'Local llama.cpp', 'demo' => 'Demo', 'openai' => 'OpenAI'];
    if (!isset($providers[$provider])) $provider = 'llamacpp';
    $flash = null;
    if (isset($_GET['review_notice']) && is_string($_GET['review_notice']) && preg_match('/\A[A-Za-z0-9]{24}\z/', $_GET['review_notice'])) {
        $key = 'lab_air_flash_' . get_current_user_id() . '_' . $_GET['review_notice'];
        $flash = get_transient($key); delete_transient($key);
    }
    $plan = $product ? get_transient(lab_air_cache_key($sku)) : false;
    if (!is_array($plan) || ($plan['proposal_id'] ?? '') !== $id || $approval !== 'approved') $plan = false;
    $run = is_array($flash) && is_array($flash['run'] ?? null) ? $flash['run'] : $plan;
    echo '<div class="air-summary"><div><span>Products</span><strong>' . esc_html((string) count($products)) . '</strong></div><div><span>Selected proposal</span>';
    lab_air_badge($approval ?: 'not generated');
    echo '</div><div><span>Provider</span><strong>' . esc_html($providers[$provider]) . '</strong></div><div><span>Backend</span>';
    lab_air_badge($connected ? 'connected' : 'unavailable'); echo '</div></div>';
    $step = !$exists ? 1 : ($approval !== 'approved' ? 2 : ($plan ? 4 : 3));
    echo '<ol class="air-stepper" aria-label="Review workflow">';
    foreach ([1=>'Generate',2=>'Review',3=>'Plan',4=>'Apply'] as $number=>$label) {
        echo '<li class="' . ($number === $step ? 'is-current' : ($number < $step ? 'is-done' : '')) . '"' . ($number === $step ? ' aria-current="step"' : '') . '><span>' . esc_html((string) $number) . '</span>' . esc_html($label) . '</li>';
    }
    echo '</ol><p class="air-principle">AI proposes. Human approves. WooCommerce applies.</p>';
    foreach ([$response, $proposal] as $maybe_error) {
        if (is_wp_error($maybe_error)) echo '<div class="notice notice-error inline"><p>' . esc_html($maybe_error->get_error_message()) . '</p></div>';
    }
    if (is_array($flash)) {
        if ($flash['error']) echo '<div class="notice notice-error inline"><p>' . esc_html($flash['error']) . '</p></div>';
        elseif ($run && $run['counts']['ERROR']) echo '<div class="notice notice-error inline"><p>' . esc_html(lab_air_error('woo_failed')->get_error_message()) . '</p></div>';
        else {
            $messages = ['propose'=>'Proposal generated. Compare every claim with the source before approval.', 'approve'=>'Proposal approved. Preview the WooCommerce PLAN next.', 'reject'=>'Proposal rejected. You can generate another version.', 'plan'=>'PLAN complete. Review all changes before applying.', 'apply'=>'Applied successfully.'];
            echo '<div class="notice notice-success inline"><p>' . esc_html($messages[$flash['action']] ?? 'Action completed.') . '</p></div>';
        }
    }
    if (!$products) {
        echo '<section class="air-card air-empty"><h2>' . ($connected ? 'No products available' : 'Connect the review service') . '</h2><p>' . ($connected ? 'Add validated products to the canonical local catalog.' : 'Start the internal ai-review container and configure the server-side token. Reload this page when it is ready.') . '</p></section></div>';
        return;
    }
    echo '<section class="air-card air-selector"><form method="get" action="' . esc_url(admin_url('admin.php')) . '"><input type="hidden" name="page" value="lab-ai-review"><label for="air-product">Product</label><div class="air-input-row"><select id="air-product" name="sku">';
    foreach ($products as $row) echo '<option value="' . esc_attr($row['sku']) . '" ' . selected($row['sku'], $sku, false) . '>' . esc_html($row['name'] . ' — ' . $row['sku']) . '</option>';
    echo '</select><button class="button" type="submit">Open review</button></div></form>';
    if ($product) {
        lab_air_form_start('propose', $sku, '', 'air-generate');
        echo '<label for="air-provider">Provider</label><div class="air-input-row"><select name="provider" id="air-provider">';
        foreach ($providers as $value=>$label) echo '<option value="' . esc_attr($value) . '" ' . selected($value, $provider, false) . '>' . esc_html($label) . '</option>';
        echo '</select><button class="button button-primary" type="submit">Generate AI Proposal</button></div></form>';
    }
    echo '</section>';
    if (!$product) { echo '<div class="notice notice-warning inline"><p>Select a valid product.</p></div></div>'; return; }
    echo '<div class="air-workspace"><main class="air-main"><section class="air-card"><div class="air-card-heading"><h2>Content review</h2>';
    lab_air_badge($approval ?: 'not generated'); echo '</div>';
    if (!$exists) echo '<div class="air-empty"><h3>Start with a proposal</h3><p>Generate content for this product, then compare it with the source here. Nothing is written to the store.</p></div>';
    else {
        echo '<div class="air-comparison-head"><span>CURRENT SOURCE</span><span>AI PROPOSAL</span></div>';
        foreach (['description'=>'Description','short_description'=>'Short description','image_alt'=>'Image ALT'] as $field=>$label) {
            echo '<div class="air-compare-row"><div><h3>' . esc_html($label) . '</h3><div class="air-copy">' . esc_html($proposal['current'][$field]) . '</div></div><div><h3>' . esc_html($label) . ' ';
            lab_air_badge($proposal['current'][$field] === $proposal['proposed'][$field] ? 'unchanged' : 'proposed');
            echo '</h3><div class="air-copy">' . esc_html($proposal['proposed'][$field]) . '</div></div></div>';
        }
        echo '<div class="air-review-footer"><p>Verify every factual claim. Generating again replaces this proposal and resets review.</p><div class="air-actions">';
        if ($approval === 'pending') {
            lab_air_button('reject','Reject',$sku,$id);
            lab_air_button('approve','Approve',$sku,$id,true);
        } elseif ($approval === 'approved') lab_air_button('plan','Preview WooCommerce PLAN',$sku,$id,true);
        else echo '<p>Rejected — generate a new proposal to continue.</p>';
        echo '</div></div>';
    }
    echo '</section>';
    if ($run) {
        echo '<section class="air-card air-plan"><div class="air-card-heading"><h2>WooCommerce ' . esc_html($run['mode']) . '</h2>';
        lab_air_badge($run['counts']['ERROR'] ? 'error' : ($run['mode']==='PLAN' ? 'read only' : 'completed'));
        echo '</div>'; lab_air_counts($run);
        echo '<div class="air-table-scroll"><table><thead><tr><th>SKU</th><th>Action</th><th>Changes</th></tr></thead><tbody>';
        $selected_changes = [];
        foreach ($run['operations'] as $operation) {
            if (strcasecmp($operation['sku'], $sku) === 0) $selected_changes = $operation['changes'];
            echo '<tr><td>' . esc_html($operation['sku'] ?: 'Catalog preflight') . '</td><td>'; lab_air_badge($operation['action']);
            echo '</td><td>' . esc_html($operation['changes'] ? count($operation['changes']) . ' fields' : '—') . '</td></tr>';
        }
        echo '</tbody></table></div><div class="air-field-status">';
        foreach (['description'=>'Description','short_description'=>'Short description','images'=>'Image / ALT'] as $key=>$label) {
            echo '<div><span>' . esc_html($label) . '</span>'; lab_air_badge(isset($selected_changes[$key]) ? 'update' : 'skip'); echo '</div>';
        }
        echo '</div><details class="air-diff"><summary>Inspect all planned field values</summary>';
        foreach ($run['operations'] as $operation) {
            foreach ($operation['changes'] as $field=>$change) {
                echo '<h4>' . esc_html($operation['sku'] . ' · ' . $field) . '</h4><div class="air-compare-row"><div class="air-copy">' . esc_html(lab_air_print_value($change['before'])) . '</div><div class="air-copy">' . esc_html(lab_air_print_value($change['after'])) . '</div></div>';
            }
        }
        echo '</details><p class="air-muted">Requests: GET ' . esc_html((string) $run['requests']['GET']) . ' · POST ' . esc_html((string) $run['requests']['POST']) . ' · PUT ' . esc_html((string) $run['requests']['PUT']) . '</p></section>';
    }
    echo '</main><aside class="air-sidebar"><section class="air-card"><span class="air-eyebrow">AI BOUNDARY</span><h2>Protected product fields</h2><div class="air-protected">';
    foreach (['Name','Price','Stock','Status'] as $field) { echo '<div><span>' . esc_html($field) . '</span>'; lab_air_badge('locked'); echo '</div>'; }
    echo '</div><p>AI cannot modify these fields.</p><p class="air-muted">The full catalog planner can reconcile source-owned fields. LOCKED describes the AI boundary, not a content-only synchronization mode. Inspect all changes before APPLY.</p></section>';
    echo '<section class="air-card air-safety"><h2>Review safeguards</h2><ul><li>Approval binds exact content</li><li>Changed source blocks APPLY</li><li>Existing store stock is preserved</li><li>Every write needs a separate action</li></ul></section>';
    if ($plan && $plan['counts']['ERROR'] === 0) {
        $write_count = $plan['counts']['CREATE'] + $plan['counts']['UPDATE'];

        if ($write_count > 0) {
            echo '<section class="air-card air-apply"><span class="air-eyebrow">EXPLICIT WRITE</span><h2>Ready to apply</h2><p>The approved content passed validation and WooCommerce preflight.</p><p>Applying will recheck the source and write the newly planned changes to the local store. The previous PLAN is not a frozen transaction.</p>';
            lab_air_button('apply','Apply approved changes',$sku,$id,true);
            echo '<p class="air-muted">Review every row, including possible source-owned field updates. Writes are not transactional.</p></section>';
        } else {
            echo '<section class="air-card air-no-write"><span class="air-eyebrow">NO WRITE NEEDED</span><h2>No changes to apply</h2><p>The current store already matches the approved proposal and catalog plan.</p><p class="air-muted">No WooCommerce write is needed.</p></section>';
        }
    }
    echo '</aside></div></div>';
}
