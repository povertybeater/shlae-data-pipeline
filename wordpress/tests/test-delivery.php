<?php
const ABSPATH = '/tmp/'; const DAY_IN_SECONDS=86400;
function add_action(...$args) {} function add_filter(...$args) {}
function current_datetime() { return new DateTimeImmutable('2026-10-02',new DateTimeZone('America/New_York')); }
function is_email($s) { return filter_var($s,FILTER_VALIDATE_EMAIL); }
$GLOBALS['options']=[];
function get_option($key,$default=false) { return $GLOBALS['options'][$key] ?? $default; }
function update_option($key,$value,$autoload=false) { $GLOBALS['options'][$key]=$value; }
function add_option($key,$value,$deprecated='',$autoload='no') { if (isset($GLOBALS['options'][$key])) { return false; } $GLOBALS['options'][$key]=$value; return true; }
function delete_option($key) { unset($GLOBALS['options'][$key]); }
function sanitize_text_field($s) { return strip_tags($s); } function wp_unslash($s) { return $s; }
function wp_json_encode($value) { return json_encode($value); }
require __DIR__.'/../shlae-lead-delivery/shlae-lead-delivery.php';
class Item {
 public $meta=[]; public $id=10;
 function get_product_id(){return 1053;} function get_quantity(){return 1;} function get_id(){return $this->id;}
 function get_meta($key){return $this->meta[$key] ?? '';}
 function add_meta_data($key,$value,$unique=true){$this->meta[$key]=$value;} function save(){}
}
class Order {
 public $id;public $meta=[];public $paid=false; public $owner=7;public $items=[];public $refund=0;
 function __construct($id,$items){$this->id=$id;$this->items=$items;}
 function get_id(){return $this->id;} function get_meta($key){return $this->meta[$key] ?? '';}
 function update_meta_data($key,$value){$this->meta[$key]=$value;} function delete_meta_data($key){unset($this->meta[$key]);}
 function get_customer_id(){return $this->owner;} function get_items(){return $this->items;} function save(){}
 function update_status($s,$n=''){$this->paid=false;}
 function is_paid(){return $this->paid;} function get_date_paid(){return new class { function getTimestamp(){return time();} };}
 function get_qty_refunded_for_item($id){return $this->refund;}
}
$n=0;function check($condition,$name){global $n;if(!$condition){throw new Exception('FAIL: '.$name);} $n++;echo "PASS: $name\n";}
$_REQUEST['shlae_lead']='BOS-ABC123';check(SHLAE_Lead_Delivery::selected()==='BOS-ABC123','uppercase source ID preserved');
$row=['id'=>'permit-test','record_date'=>'2026-10-01','expires_on'=>'2026-10-31','contact_checked_at'=>'2026-10-02','contact_verification'=>'contact_checked','business_name'=>'Example','email'=>'office@example.com','phone'=>'','contact_source_url'=>'https://example.com/contact','max_buyers'=>1];
check(SHLAE_Lead_Delivery::valid($row),'reviewed fresh contact accepted');
check(!SHLAE_Lead_Delivery::valid(array_replace($row,['record_date'=>'2026-08-01'])),'stale permit rejected');
check(!SHLAE_Lead_Delivery::valid(array_replace($row,['contact_verification'=>'business_matched'])),'unverified contact rejected');
check(!SHLAE_Lead_Delivery::valid(array_replace($row,['expiration_date'=>'2026-10-01'])),'expired permit rejected');
SHLAE_Lead_Delivery::save_inventory([$row]);
$item=new Item();$item->meta['Lead record']=$row['id'];$item->meta['_shlae_record']=json_encode($row);
$order=new Order(100,[$item]);SHLAE_Lead_Delivery::reserve($order);
check(SHLAE_Lead_Delivery::remaining($row)===0,'reservation consumes buyer limit');
$other=new Item();$other->meta['Lead record']=$row['id'];$other->meta['_shlae_record']=json_encode($row);$second=new Order(101,[$other]);
try {SHLAE_Lead_Delivery::reserve($second);$blocked=false;}catch(Exception $e){$blocked=true;}
check($blocked,'second buyer blocked at cap');
check(!SHLAE_Lead_Delivery::allowed($order,$item,7),'unpaid buyer denied');
$order->paid=true;
check(SHLAE_Lead_Delivery::allowed($order,$item,7),'paid owner allowed');
check(!SHLAE_Lead_Delivery::allowed($order,$item,0),'guest denied');
check(!SHLAE_Lead_Delivery::allowed($order,$item,8),'other account denied');
$order->refund=-1;
check(!SHLAE_Lead_Delivery::allowed($order,$item,7),'refunded record denied');$order->refund=0;
SHLAE_Lead_Delivery::release(100,'pending','cancelled',$order);
check(SHLAE_Lead_Delivery::remaining($row)===1,'cancelled order releases slot');
check(!SHLAE_Lead_Delivery::allowed($order,$item,7),'released claim cannot download');
check(SHLAE_Lead_Delivery::csv_value('=HYPERLINK("x")')[0]==="'",'CSV formula neutralized');
check(SHLAE_Lead_Delivery::csv_value('Ordinary text')==='Ordinary text','ordinary CSV value unchanged');
check(SHLAE_Lead_Delivery::test_email(true,new class {function get_meta($k){return true;}})===false,'test email suppressed');
echo "$n checks passed\n";
