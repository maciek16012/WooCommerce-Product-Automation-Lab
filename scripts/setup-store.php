<?php
/** Local-only deterministic setup. Run with docker compose exec wordpress php /tmp/lab-setup.php */
require '/var/www/html/wp-load.php';
require_once ABSPATH.'wp-admin/includes/image.php';
if (!in_array(parse_url(home_url(), PHP_URL_HOST), ['localhost','127.0.0.1'],true)) { throw new Exception('Local store only'); }
update_option('blogname','Biurko / Lab');
update_option('blogdescription','Dobrze zaprojektowane miejsce pracy.');
update_option('woocommerce_store_address','Pracownia demonstracyjna');
update_option('woocommerce_store_city','Warszawa');
update_option('woocommerce_store_postcode','00-001');
update_option('woocommerce_default_country','PL');
update_option('woocommerce_currency','PLN');
update_option('woocommerce_allowed_countries','specific');
update_option('woocommerce_specific_allowed_countries',['PL']);
update_option('woocommerce_ship_to_countries','specific');
update_option('woocommerce_specific_ship_to_countries',['PL']);
update_option('woocommerce_calc_taxes','no');
update_option('woocommerce_price_num_decimals','2');
update_option('woocommerce_price_decimal_sep',',');
update_option('woocommerce_price_thousand_sep',' ');
update_option('woocommerce_currency_pos','right_space');
update_option('woocommerce_coming_soon','no');
update_option('woocommerce_coming_soon_store_pages_only','no');
update_option('woocommerce_enable_guest_checkout','yes');
update_option('woocommerce_enable_signup_and_login_from_checkout','no');
update_option('woocommerce_enable_myaccount_registration','no');
update_option('woocommerce_manage_stock','yes');
update_option('woocommerce_track_stock','yes');
update_option('woocommerce_enable_reviews','no');
update_option('woocommerce_demo_store','no');
update_option('blog_public',0);
update_option('timezone_string','Europe/Warsaw');
update_option('woocommerce_allow_tracking','no');
$profile=get_option('woocommerce_onboarding_profile',[]); $profile['completed']=true; update_option('woocommerce_onboarding_profile',$profile);
foreach(['bacs','cheque'] as $gateway) update_option('woocommerce_'.$gateway.'_settings',['enabled'=>'no']);
update_option('woocommerce_cod_settings',['enabled'=>'yes','title'=>'Zamówienie testowe — bez płatności','description'=>'Tryb demonstracyjny. Nie pobieramy pieniędzy i nie wysyłamy produktów.','instructions'=>'To fikcyjne zamówienie w lokalnym laboratorium. Nie wymaga płatności.','enable_for_virtual'=>'yes']);
function lab_page($slug,$title,$content) {
    $p=get_page_by_path($slug);
    $args=['post_title'=>$title,'post_name'=>$slug,'post_content'=>$content,'post_status'=>'publish','post_type'=>'page'];
    if($p) $args['ID']=$p->ID;
    $id=wp_insert_post($args,true); if(is_wp_error($id)) throw new Exception($id->get_error_message()); return $id;
}
$front=lab_page('start','Dobrze urządzone biurko.','');
update_option('show_on_front','page'); update_option('page_on_front',$front);
update_option('woocommerce_shop_page_id',lab_page('sklep','Wszystko na swoim miejscu',''));
update_option('woocommerce_cart_page_id',lab_page('koszyk','Twój koszyk','[woocommerce_cart]'));
update_option('woocommerce_checkout_page_id',lab_page('zamowienie','Dokończ zamówienie testowe','[woocommerce_checkout]'));
lab_page('o-pracowni','O pracowni','Biurko / Lab to fikcyjna marka akcesoriów do stanowiska komputerowego. Ten lokalny sklep jest częścią projektu portfolio WooCommerce Product Automation Lab. Produkty, parametry i ceny są demonstracyjne. Nie przyjmujemy rzeczywistych płatności i nie realizujemy dostaw. Ilustracje powstały specjalnie na potrzeby projektu.');
lab_page('informacje','Informacje o demonstracji','Sklep działa wyłącznie lokalnie. Wszystkie produkty i zamówienia są fikcyjne. W formularzu używaj wyłącznie danych testowych. Dostawa testowa: 12,90 zł; bezpłatna od 250 zł. Dane koszyka i zamówienia są zapisywane w lokalnej bazie WordPress. Wysyłka e-mail jest wyłączona. To demonstracja techniczna, a nie oferta sprzedaży.');
foreach(['peryferia'=>'Peryferia','kable'=>'Kable i połączenia','organizacja'=>'Organizacja biurka'] as $slug=>$name) {
    if(!get_term_by('slug',$slug,'product_cat')) wp_insert_term($name,'product_cat',['slug'=>$slug]);
}
$zones=WC_Shipping_Zones::get_zones(); $zone=null;
foreach($zones as $z) if($z['zone_name']==='Polska — demo') $zone=new WC_Shipping_Zone($z['id']);
if(!$zone) { $zone=new WC_Shipping_Zone(); $zone->set_zone_name('Polska — demo'); $zone->add_location('PL','country'); $zone->save(); }
$zone->set_zone_order(-1); $zone->save();
$methods=$zone->get_shipping_methods(); $flat=null; $free=null;
foreach($methods as $m) { if($m->id==='flat_rate') $flat=$m->instance_id; if($m->id==='free_shipping') $free=$m->instance_id; }
if(!$flat) $flat=$zone->add_shipping_method('flat_rate');
if(!$free) $free=$zone->add_shipping_method('free_shipping');
update_option('woocommerce_flat_rate_'.$flat.'_settings',['title'=>'Dostawa testowa','tax_status'=>'none','cost'=>'12.90']);
update_option('woocommerce_free_shipping_'.$free.'_settings',['title'=>'Darmowa dostawa testowa','requires'=>'min_amount','min_amount'=>'250']);
WC_Cache_Helper::get_transient_version('shipping',true);
update_option('woocommerce_checkout_privacy_policy_text','Demonstracja lokalna. Wpisz wyłącznie fikcyjne dane. Zamówienie nie wymaga płatności i nie będzie wysłane.');
update_option('woocommerce_terms_page_id',0);
$manifest=[];
foreach(glob('/tmp/lab-assets/*.png') as $src) {
    $slug=basename($src,'.png');
    if($slug==='hero') continue;
    $found=get_posts(['post_type'=>'attachment','meta_key'=>'_lab_asset','meta_value'=>$slug,'numberposts'=>1]);
    if($found) { $manifest[$slug]=$found[0]->ID; continue; }
    $upload=wp_upload_bits(basename($src),null,file_get_contents($src));
    if($upload['error']) throw new Exception($upload['error']);
    $id=wp_insert_attachment(['post_mime_type'=>'image/png','post_title'=>'Biurko Lab — '.$slug,'post_status'=>'inherit'],$upload['file']);
    wp_update_attachment_metadata($id,wp_generate_attachment_metadata($id,$upload['file']));
    update_post_meta($id,'_lab_asset',$slug); $manifest[$slug]=$id;
}
file_put_contents('/tmp/lab-media.json',json_encode($manifest,JSON_PRETTY_PRINT));
switch_theme('biurko-lab');
update_option('permalink_structure','/%postname%/'); flush_rewrite_rules(true);
echo json_encode(['configured'=>true,'media'=>$manifest,'front_page'=>$front,'theme'=>get_option('stylesheet')],JSON_PRETTY_PRINT);
