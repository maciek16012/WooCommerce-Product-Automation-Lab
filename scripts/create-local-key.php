<?php
require '/var/www/html/wp-load.php';
if (!in_array(parse_url(home_url(), PHP_URL_HOST),['localhost','127.0.0.1'],true)) throw new Exception('Local only');
$user=get_user_by('login','lab_sync');
if(!$user) {
    $id=wp_insert_user(['user_login'=>'lab_sync','user_pass'=>wp_generate_password(48,true,true),'user_email'=>'sync@example.invalid','role'=>'shop_manager','display_name'=>'Lab Synchronizer']);
    if(is_wp_error($id)) throw new Exception('Cannot create test user');
} else $id=$user->ID;
// Run once. Do not rotate silently or print the credentials.
$description='Portfolio CSV synchronizer';
global $wpdb;
if($wpdb->get_var($wpdb->prepare("SELECT key_id FROM {$wpdb->prefix}woocommerce_api_keys WHERE description=%s",$description))) { echo "Key already exists; keep the local credential file.\n"; exit; }
$key='ck_'.bin2hex(random_bytes(20)); $secret='cs_'.bin2hex(random_bytes(20));
$ok=$wpdb->insert($wpdb->prefix.'woocommerce_api_keys',['user_id'=>$id,'description'=>$description,'permissions'=>'read_write','consumer_key'=>wc_api_hash($key),'consumer_secret'=>$secret,'truncated_key'=>substr($key,-7)]);
if(!$ok) throw new Exception('Cannot store key');
umask(0077);
file_put_contents('/tmp/lab-credentials.json',json_encode(['WC_URL'=>home_url(),'WC_CONSUMER_KEY'=>$key,'WC_CONSUMER_SECRET'=>$secret],JSON_PRETTY_PRINT));
echo "Read/write key created for lab_sync. Credentials saved to private temporary file.\n";
