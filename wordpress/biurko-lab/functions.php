<?php
add_action('after_setup_theme',function(){add_theme_support('title-tag');add_theme_support('post-thumbnails');add_theme_support('woocommerce');add_theme_support('wc-product-gallery-lightbox');add_theme_support('wc-product-gallery-slider');});
add_action('wp_enqueue_scripts',function(){wp_enqueue_style('lab',get_stylesheet_uri(),[],filemtime(get_stylesheet_directory().'/style.css'));});
remove_action('woocommerce_before_main_content','woocommerce_output_content_wrapper',10);
remove_action('woocommerce_after_main_content','woocommerce_output_content_wrapper_end',10);
add_action('woocommerce_before_main_content',function(){echo '<main id="main" class="wrap shop-main">';},10);
add_action('woocommerce_after_main_content',function(){echo '</main>';},10);
remove_action('woocommerce_sidebar','woocommerce_get_sidebar',10);
add_filter('loop_shop_columns',fn()=>3);
add_filter('loop_shop_per_page',fn()=>12);
add_filter('woocommerce_product_description_heading',fn()=>'Przemyślane detale');
add_filter('woocommerce_product_tabs',function($tabs){unset($tabs['reviews']);return $tabs;});
add_filter('woocommerce_checkout_fields',function($fields){unset($fields['billing']['billing_company']);$fields['billing']['billing_phone']['required']=false;return $fields;});
add_filter('woocommerce_checkout_privacy_policy_text',fn()=> 'Demonstracja lokalna. Wpisz fikcyjne dane. Zamówienie nie wiąże się z płatnością ani wysyłką.');
add_filter('woocommerce_cart_shipping_method_full_label',function($label,$method){return $label;},10,2);
function lab_category_nav(){echo '<nav class="category-nav" aria-label="Kategorie produktów"><a href="'.esc_url(wc_get_page_permalink('shop')).'">Wszystkie produkty</a>'; foreach(['peryferia','kable','organizacja'] as $slug){$t=get_term_by('slug',$slug,'product_cat');if($t) echo '<a href="'.esc_url(get_term_link($t)).'">'.esc_html($t->name).'</a>';} echo '</nav>';}
add_action('woocommerce_before_shop_loop','lab_category_nav',5);
add_filter('woocommerce_order_button_text',fn()=> 'Złóż zamówienie testowe');
add_filter('woocommerce_get_privacy_policy_text',fn($text)=> 'Demonstracja lokalna. Wpisz wyłącznie fikcyjne dane. Zamówienie nie wymaga płatności i nie będzie wysłane.');
