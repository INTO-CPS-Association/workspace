mc admin user add local {USER_STORE_KEY_ID} {USER_STORE_SECRET_KEY}
mc admin policy create local user-policy /tmp/syssec/{USER_STORE_KEY_ID}.json
mc admin policy attach local user-policy --user {USER_STORE_KEY_ID}