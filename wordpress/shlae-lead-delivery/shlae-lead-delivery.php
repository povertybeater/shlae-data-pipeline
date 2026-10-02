<?php
/**
 * Plugin Name: SHLAE Selected Lead Delivery
 * Description: Selected-record checkout, private CSV delivery and reviewed inventory.
 * Version: 0.1.1
 */
if (!defined('ABSPATH')) { exit; }
final class SHLAE_Lead_Delivery {
    const PRODUCT = 1053;
    const OPTION = 'shlae_private_inventory_v1';
    const FIELDS = ['id','sector','business_name','company_role','contact_name','contact_role','contact_type','email','phone','website','street_address','city','state','zip','description','value','permit_number','permit_type','permit_status','record_date','expiration_date','source_url','contact_verification','verification_method','contact_checked_at','contact_source_url','contract_status','date_checked'];
    static function boot() {
        add_action('admin_menu', [__CLASS__, 'menu']);
        add_action('admin_post_shlae_import', [__CLASS__, 'import']);
        add_action('admin_post_shlae_test', [__CLASS__, 'test']);
        add_action('admin_post_shlae_csv', [__CLASS__, 'download']);
        add_action('admin_post_nopriv_shlae_csv', [__CLASS__, 'download']);
        add_shortcode('shlae_lead_catalog', [__CLASS__, 'catalog']);
        add_action('woocommerce_before_add_to_cart_button', [__CLASS__, 'selection']);
        add_filter('woocommerce_add_to_cart_validation', [__CLASS__, 'validate_cart'], 10, 3);
        add_filter('woocommerce_add_cart_item_data', [__CLASS__, 'cart_data'], 10, 3);
        add_filter('woocommerce_get_item_data', [__CLASS__, 'cart_label'], 10, 2);
        add_action('woocommerce_check_cart_items', [__CLASS__, 'check_cart']);
        add_action('woocommerce_checkout_create_order_line_item', [__CLASS__, 'snapshot'], 10, 4);
        add_action('woocommerce_checkout_order_created', [__CLASS__, 'reserve']);
        add_action('woocommerce_store_api_checkout_order_processed', [__CLASS__, 'reserve']);
        add_action('woocommerce_order_status_changed', [__CLASS__, 'release'], 10, 4);
        add_filter('woocommerce_customer_available_downloads', [__CLASS__, 'account_downloads'],10,2);
        add_action('woocommerce_thankyou', [__CLASS__, 'thankyou']);
        add_action('woocommerce_email_after_order_table', [__CLASS__, 'email_links'], 10, 4);
        foreach (['new_order','cancelled_order','failed_order','customer_processing_order','customer_completed_order','customer_on_hold_order','customer_invoice','customer_note','customer_refunded_order'] as $type) {
            add_filter('woocommerce_email_enabled_' . $type, [__CLASS__, 'test_email'], 10, 2);
        }
        add_action('shlae_sync_private_inventory', [__CLASS__, 'sync']);
        if (!wp_next_scheduled('shlae_sync_private_inventory')) {
            wp_schedule_event(time() + 3600, 'daily', 'shlae_sync_private_inventory');
        }
    }
    static function test_email($enabled, $order) {
        return is_object($order) && method_exists($order, 'get_meta') && $order->get_meta('_shlae_test') ? false : $enabled;
    }
    static function day() { return current_datetime()->format('Y-m-d'); }
    static function valid($row) {
        if (!is_array($row) || empty($row['id']) || !preg_match('/^[a-zA-Z0-9_-]{1,80}$/', $row['id'])) { return false; }
        $date = substr((string)($row['record_date'] ?? ''), 0, 10);
        $checked = substr((string)($row['contact_checked_at'] ?? ''), 0, 10);
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/',$date) || !preg_match('/^\d{4}-\d{2}-\d{2}$/',$checked)) { return false; }
        $cutoff = current_datetime()->modify('-30 days')->format('Y-m-d');
        return $date > $cutoff && $date <= self::day() && $checked > $cutoff && $checked <= self::day()
            && ($row['expires_on'] ?? '') > self::day()
            && !in_array(strtolower($row['permit_status'] ?? ''), ['closed','expired','revoked','cancelled','canceled','void'], true)
            && (empty($row['expiration_date']) || substr($row['expiration_date'],0,10) >= self::day())
            && ($row['contact_verification'] ?? '') === 'contact_checked'
            && !empty($row['business_name']) && (!empty($row['email']) && is_email($row['email']) || (strlen(preg_replace('/\D/', '', $row['phone'] ?? '')) >= 10 && strlen(preg_replace('/\D/', '', $row['phone'] ?? '')) <= 15))
            && str_starts_with($row['contact_source_url'] ?? '', 'https://');
    }
    static function inventory() {
        $rows = get_option(self::OPTION, []);
        $clean=is_array($rows) ? array_filter($rows, [__CLASS__, 'valid']) : [];
        if ($clean !== $rows) { update_option(self::OPTION,$clean,false); }
        return $clean;
    }
    static function lead($id) { return self::inventory()[$id] ?? null; }
    static function claims($id, $limit) {
        $count = 0;
        for ($slot=1; $slot <= $limit; $slot++) {
            if (get_option('shlae_claim_' . $id . '_' . $slot, false) !== false) { $count++; }
        }
        return $count;
    }
    static function remaining($row) {
        $limit = max(1, min(100, (int)($row['max_buyers'] ?? 5)));
        return $limit - self::claims($row['id'], $limit);
    }
    static function menu() { add_submenu_page('woocommerce', 'SHLAE Leads', 'SHLAE Leads', 'manage_woocommerce', 'shlae-leads', [__CLASS__, 'admin']); }
    static function admin() {
        if (!current_user_can('manage_woocommerce')) { return; }
        echo '<div class="wrap"><h1>SHLAE Leads</h1><p>Private inventory is stored in WordPress, never in publicly accessible CSV files.</p>';
        echo '<p>Source-checked means published contact details were checked. It does not mean a successful call, email delivery or an open bid.</p>';
        if (isset($_GET['result'])) { echo '<div class="notice notice-success"><p>' . esc_html(sanitize_text_field(wp_unslash($_GET['result']))) . '</p></div>'; }
        echo '<p>Eligible records: ' . count(self::inventory()) . '. Default buyer limit: 5 per record. Import max_buyers to change it.</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="shlae_import">';
        wp_nonce_field('shlae_import');
        echo '<label for="shlae_records">Reviewed private records JSON</label><br><textarea id="shlae_records" name="records" rows="8" cols="95"></textarea><p>Imports replace inventory. Sold order snapshots are preserved.</p><button class="button button-primary">Import reviewed records</button></form>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="shlae_test">';
        wp_nonce_field('shlae_test');
        echo '<p><button class="button">Run no-charge integration test</button> Creates a clearly marked test order for your account. No customer emails or payment gateway calls.</p></form>';
        echo '<p>Catalog shortcode: <code>[shlae_lead_catalog]</code>. Feed synchronization reads SHLAE_PRIVATE_FEED_KEY from server configuration; until configured, import reviewed records here.</p>';
        $test = (int)get_option('shlae_last_test_order', 0);
        if ($test && ($order=wc_get_order($test))) { self::links($order); }
        echo '</div>';
    }
    static function save_inventory($rows) {
        if (!is_array($rows) || !array_is_list($rows)) { throw new Exception('Records must be a JSON array.'); }
        $accepted=[];
        foreach ($rows as $row) {
            if (self::valid($row)) {
                $row['contact_type']=self::contact_type($row);
                $row['max_buyers']=max(1,min(100,(int)($row['max_buyers'] ?? 5)));
                $accepted[$row['id']]=$row;
            }
        }
        update_option(self::OPTION, $accepted, false);
        return count($accepted);
    }
    static function import() {
        if (!current_user_can('manage_woocommerce')) { wp_die('Not permitted', '', ['response'=>403]); }
        check_admin_referer('shlae_import');
        try {
            $rows=json_decode(wp_unslash($_POST['records'] ?? ''),true,512,JSON_THROW_ON_ERROR);
            $count=self::save_inventory($rows);
        } catch (Throwable $e) { wp_die('Invalid import: ' . esc_html($e->getMessage())); }
        wp_safe_redirect(admin_url('admin.php?page=shlae-leads&result=' . rawurlencode("Imported $count eligible records."))); exit;
    }
    static function sync() {
        $encoded=defined('SHLAE_PRIVATE_FEED_KEY') ? SHLAE_PRIVATE_FEED_KEY : getenv('SHLAE_PRIVATE_FEED_KEY');
        $key=base64_decode((string)$encoded,true);
        if (!$key || strlen($key)!==32) { return; }
        $response=wp_safe_remote_get('https://shlae.com/wp-content/uploads/leads/private_leads.enc.json',['timeout'=>30]);
        if (is_wp_error($response) || wp_remote_retrieve_response_code($response)!==200) { return; }
        try {
            $env=json_decode(wp_remote_retrieve_body($response),true,512,JSON_THROW_ON_ERROR);
            if (($env['version'] ?? 0)!==1 || ($env['algorithm'] ?? '')!=='AES-256-GCM') { return; }
            $nonce=base64_decode($env['nonce'],true); $cipher=base64_decode($env['ciphertext'],true);
            if (!$nonce || strlen($nonce)!==12 || !$cipher || strlen($cipher)<16) { return; }
            $clear=openssl_decrypt(substr($cipher,0,-16),'aes-256-gcm',$key,OPENSSL_RAW_DATA,$nonce,substr($cipher,-16),'shlae-private-feed-v1');
            if ($clear===false) { return; }
            self::save_inventory(json_decode($clear,true,512,JSON_THROW_ON_ERROR));
        } catch (Throwable $e) { /* Preserve inventory on source/decryption failure. */ }
    }
    static function catalog() {
        if (!function_exists('wc_get_product')) { return ''; }
        $product=wc_get_product(self::PRODUCT);
        if (!$product || !$product->is_purchasable()) { return '<p>Reviewed leads are being prepared for purchase.</p>'; }
        $html='<p>Boston permit activity with source-checked business contact details. Issued permits do not establish an open bid or buying intent. Blank fields remain blank. Email delivery and phone response have not been tested.</p><table><thead><tr><th>Record</th><th>Industry</th><th>Issued</th><th>Contact fields</th><th>Remaining purchases</th><th>Purchase</th></tr></thead><tbody>';
        foreach (self::inventory() as $row) {
            $remaining=self::remaining($row); if ($remaining<=0) { continue; }
            $fields=(!empty($row['email']) ? 'Published business email; ' : '') . (!empty($row['phone']) ? 'published business phone' : '');
            $url=add_query_arg(['add-to-cart'=>self::PRODUCT,'shlae_lead'=>$row['id'],'_shlae_nonce'=>wp_create_nonce('shlae_select_'.$row['id'])],wc_get_cart_url());
            $buy=is_user_logged_in() ? '<a href="'.esc_url($url).'">Buy '.wp_kses_post($product->get_price_html()).'</a>' : '<a href="'.esc_url(wc_get_page_permalink('myaccount')).'">Sign in to purchase</a>';
            $html.='<tr><td>'.esc_html($row['id']).'</td><td>'.esc_html($row['sector']).'</td><td>'.esc_html(substr($row['record_date'],0,10)).'</td><td>'.esc_html($fields).'</td><td>'.(int)$remaining.'</td><td>'.$buy.'</td></tr>';
        }
        return $html.'</tbody></table>';
    }
    static function selected() { $id=sanitize_text_field(wp_unslash($_REQUEST['shlae_lead'] ?? '')); return preg_match('/^[a-zA-Z0-9_-]{1,80}$/',$id) ? $id : ''; }
    static function selection() {
        global $product; if (!$product || $product->get_id()!==self::PRODUCT) { return; }
        echo '<p>Select the specific record before checkout. Downloads are available in your account after payment.</p><label>Lead record <select name="shlae_lead"><option value="">Select a lead</option>';
        foreach (self::inventory() as $row) { if (self::remaining($row)>0) { echo '<option value="'.esc_attr($row['id']).'">'.esc_html($row['id'].' — '.$row['sector'].' — '.substr($row['record_date'],0,10)).'</option>'; } }
        echo '</select></label>'; wp_nonce_field('shlae_product_select','_shlae_product_nonce');
    }
    static function validate_cart($passed,$product_id,$quantity) {
        if ((int)$product_id!==self::PRODUCT) { return $passed; }
        $id=self::selected(); $row=self::lead($id);
        $nonce=wp_unslash($_REQUEST['_shlae_nonce'] ?? '');
        $product_nonce=wp_unslash($_REQUEST['_shlae_product_nonce'] ?? '');
        if (!is_user_logged_in() || !$row || self::remaining($row)<=0 || (int)$quantity!==1
            || (!wp_verify_nonce($nonce,'shlae_select_'.$id) && !wp_verify_nonce($product_nonce,'shlae_product_select'))) {
            wc_add_notice('Sign in and select one available reviewed lead from the catalog.','error'); return false;
        }
        foreach (WC()->cart->get_cart() as $item) { if (($item['shlae_lead'] ?? '')===$id) { wc_add_notice('This lead is already in your cart.','error'); return false; } }
        return $passed;
    }
    static function cart_data($data,$product_id,$variation_id) {
        if ((int)$product_id===self::PRODUCT) { $data['shlae_lead']=self::selected(); }
        return $data;
    }
    static function cart_label($data,$item) { if (!empty($item['shlae_lead'])) { $data[]=['key'=>'Lead record','value'=>$item['shlae_lead']]; } return $data; }
    static function check_cart() {
        foreach (WC()->cart->get_cart() as $item) {
            if ((int)$item['product_id']!==self::PRODUCT) { continue; }
            $row=self::lead($item['shlae_lead'] ?? '');
            if (!is_user_logged_in() || !$row || self::remaining($row)<=0 || (int)$item['quantity']!==1) { wc_add_notice('A selected lead is unavailable. Remove it and choose an available record.','error'); }
        }
    }
    static function snapshot($item,$cart_key,$values,$order) {
        if ((int)$item->get_product_id()!==self::PRODUCT) { return; }
        $row=self::lead($values['shlae_lead'] ?? '');
        if (!$row || !is_user_logged_in() || (int)$item->get_quantity()!==1) { throw new Exception('Invalid lead selection.'); }
        $item->add_meta_data('Lead record',$row['id'],true);
        $item->add_meta_data('_shlae_record',wp_json_encode($row),true);
    }
    static function reserve($order) {
        if (!is_object($order)) { $order=wc_get_order($order); }
        if (!$order || $order->get_meta('_shlae_reserved') || $order->get_meta('_shlae_test')) { return; }
        $claims=[]; $seen=[];
        try {
            foreach ($order->get_items() as $item) {
                if ((int)$item->get_product_id()!==self::PRODUCT) { continue; }
                $id=(string)$item->get_meta('Lead record'); $row=self::lead($id);
                if (isset($seen[$id])) { throw new Exception('Duplicate lead selection.'); }
                $seen[$id]=true;
                if (!$row || !$order->get_customer_id() || (int)$item->get_quantity()!==1) { throw new Exception('Lead selection is no longer available.'); }
                if (!$item->get_meta('_shlae_record')) { $item->add_meta_data('_shlae_record',wp_json_encode($row),true); }
                $found=false;
                for ($slot=1; $slot<=$row['max_buyers']; $slot++) {
                    $name='shlae_claim_'.$id.'_'.$slot;
                    if (add_option($name,(string)$order->get_id(),'','no')) { $claims[]=$name; $item->add_meta_data('_shlae_claim',$name,true); $found=true; break; }
                }
                if (!$found) { throw new Exception('This lead has reached its purchase limit.'); }
                $item->save();
            }
            if ($claims) { $order->update_meta_data('_shlae_reserved',true); $order->save(); }
        } catch (Throwable $e) {
            foreach ($claims as $name) { delete_option($name); }
            $order->update_status('failed','SHLAE lead reservation failed.');
            throw $e;
        }
    }
    static function release($order_id,$old,$new,$order) {
        if (!in_array($new,['cancelled','failed','refunded'],true)) { return; }
        foreach ($order->get_items() as $item) {
            $name=$item->get_meta('_shlae_claim');
            if ($name && (int)get_option($name) === (int)$order_id) { delete_option($name); }
        }
        $order->delete_meta_data('_shlae_reserved'); $order->save();
    }
    static function allowed($order,$item,$user_id) {
        if (!$order || !$item || !$user_id || (int)$order->get_customer_id()!==(int)$user_id || !$order->is_paid()
            || (int)$item->get_product_id()!==self::PRODUCT || !$item->get_meta('_shlae_record')
            || abs($order->get_qty_refunded_for_item($item->get_id()))>0) { return false; }
        $paid=$order->get_date_paid();
        if (!$paid || $paid->getTimestamp()+30*DAY_IN_SECONDS < time()) { return false; }
        if ($order->get_meta('_shlae_test')) { return true; }
        $claim=$item->get_meta('_shlae_claim');
        return $claim && (int)get_option($claim)===(int)$order->get_id();
    }
    static function url($order,$item) { return wp_nonce_url(add_query_arg(['action'=>'shlae_csv','order'=>$order->get_id(),'item'=>$item->get_id()],admin_url('admin-post.php')),'shlae_csv_'.$order->get_id().'_'.$item->get_id()); }
    static function links($order) {
        if (!$order || !$order->is_paid()) { return; }
        foreach ($order->get_items() as $item) {
            if (self::allowed($order,$item,get_current_user_id())) { echo '<p><a href="'.esc_url(self::url($order,$item)).'">Download lead '.esc_html($item->get_meta('Lead record')).' (CSV)</a></p>'; }
        }
    }
    static function thankyou($id) { self::links(wc_get_order($id)); }
    static function email_links($order,$admin,$plain,$email) {
        if ($admin || !$order->is_paid() || $order->get_meta('_shlae_test')) { return; }
        $has=false; foreach($order->get_items() as $item) { if ($item->get_meta('_shlae_record')) { $has=true; break; } }
        if (!$has) { return; }
        $url=wc_get_account_endpoint_url('downloads');
        echo $plain ? "\nYour selected lead files are available after sign-in: $url\n" : '<p>Your selected lead files are available after sign-in in <a href="'.esc_url($url).'">My Account → Downloads</a>.</p>';
    }
    static function account_downloads($downloads,$customer_id=0) {
        if (!is_user_logged_in() || (int)$customer_id!==get_current_user_id()) { return $downloads; }
        $orders=wc_get_orders(['customer_id'=>get_current_user_id(),'status'=>['processing','completed'],'limit'=>-1]);
        foreach ($orders as $order) { foreach($order->get_items() as $item) {
            if (!self::allowed($order,$item,get_current_user_id())) { continue; }
            $url=self::url($order,$item); $id=$item->get_meta('Lead record');
            $downloads[]=['download_url'=>$url,'download_id'=>'shlae_'.$item->get_id(),'product_id'=>self::PRODUCT,'product_name'=>'Boston lead '.$id,'product_url'=>get_permalink(self::PRODUCT),'download_name'=>'Lead '.$id.' CSV','order_id'=>$order->get_id(),'order_key'=>$order->get_order_key(),'downloads_remaining'=>'','access_expires'=>date('Y-m-d',$order->get_date_paid()->getTimestamp()+30*DAY_IN_SECONDS),'file'=>['name'=>'Lead '.$id.' CSV','file'=>$url]];
        } }
        return $downloads;
    }
    static function contact_type($row) {
        $type=strtolower(trim((string)($row['contact_type'] ?? 'general')));
        return in_array($type,['general','executive','department','staff'],true) ? $type : 'general';
    }
    static function csv_value($value) {
        $value=is_scalar($value) ? (string)$value : '';
        return preg_match('/^[\s]*[=+@-]/',$value) ? "'".$value : $value;
    }
    static function download() {
        $id=absint($_GET['order'] ?? 0); $item_id=absint($_GET['item'] ?? 0);
        $order=wc_get_order($id); $item=$order ? $order->get_item($item_id) : null;
        if (!self::allowed($order,$item,get_current_user_id()) || !wp_verify_nonce(wp_unslash($_GET['_wpnonce'] ?? ''),'shlae_csv_'.$id.'_'.$item_id)) { wp_die('Download unavailable. Sign in to the purchasing account and use My Account → Downloads.','',['response'=>403]); }
        $row=json_decode($item->get_meta('_shlae_record'),true);
        if (!is_array($row)) { wp_die('Invalid record.','',['response'=>404]); }
        nocache_headers(); header('X-Content-Type-Options: nosniff'); header('Content-Type: text/csv; charset=utf-8');
        header('Content-Disposition: attachment; filename="shlae-'.$item_id.'.csv"');
        $stream=fopen('php://output','w'); fputcsv($stream,self::FIELDS,',','"','');
        fputcsv($stream,array_map(fn($field)=>self::csv_value($field==='contact_type' ? self::contact_type($row) : ($row[$field] ?? '')),self::FIELDS),',','"',''); fclose($stream); exit;
    }
    static function test() {
        if (!current_user_can('manage_woocommerce')) { wp_die('Not permitted.','',['response'=>403]); }
        check_admin_referer('shlae_test');
        $rows=self::inventory(); $row=reset($rows); $product=wc_get_product(self::PRODUCT);
        if (!$row || !$product) { wp_die('Import a reviewed record first.'); }
        $order=wc_create_order(['customer_id'=>get_current_user_id(),'created_via'=>'shlae-integration-test']);
        $order->update_meta_data('_shlae_test',true); $order->save();
        $item=new WC_Order_Item_Product(); $item->set_product($product); $item->set_quantity(1); $item->set_subtotal(0); $item->set_total(0);
        $item->add_meta_data('Lead record',$row['id'],true); $item->add_meta_data('_shlae_record',wp_json_encode($row),true);
        $order->add_item($item); $order->calculate_totals(); $order->save();
        $test_items=$order->get_items(); $saved=reset($test_items);
        $unpaid=!self::allowed($order,$saved,get_current_user_id());
        $order->set_date_paid(time()); $order->update_status('completed','No-charge SHLAE integration test; no gateway called.');
        $paid=self::allowed($order,$saved,get_current_user_id());
        $outsider=!self::allowed($order,$saved,0) && !self::allowed($order,$saved,get_current_user_id()+1000000);
        update_option('shlae_last_test_order',$order->get_id(),false);
        $result=$unpaid && $paid && $outsider ? 'PASS: unpaid denied; paid owner allowed; guest and other account denied. Test order '.$order->get_id().' — no charge, no emails.' : 'FAIL: review access checks.';
        wp_safe_redirect(admin_url('admin.php?page=shlae-leads&result='.rawurlencode($result))); exit;
    }
}
add_action('plugins_loaded', function() { if (class_exists('WooCommerce')) { SHLAE_Lead_Delivery::boot(); } });
