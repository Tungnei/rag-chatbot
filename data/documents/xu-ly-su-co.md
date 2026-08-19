# Sổ tay xử lý sự cố

## Truy vấn trả về lỗi máy chủ

Triệu chứng: điểm cuối truy vấn trả mã lỗi năm trăm, giao diện hiện thông báo lỗi kèm
mã số. Việc đầu tiên là đọc nhật ký của tiến trình ứng dụng để lấy vết ngoại lệ, đừng
đoán từ mã lỗi.

Nguyên nhân thường gặp nhất là chứng thực truy cập dịch vụ sinh vector đã hết hạn hoặc
bị thu hồi. Điều gây bối rối là điểm cuối kiểm tra tình trạng vẫn có thể báo tốt, vì nó
gọi một điểm cuối khác không đòi chứng thực. Khi nghi ngờ, hãy thử gọi trực tiếp dịch
vụ sinh vector bằng đúng chứng thực đang cấu hình.

Nguyên nhân thứ hai là kho vector không truy cập được. Trường hợp này điểm cuối kiểm
tra tình trạng sẽ báo đúng, nên phân biệt được ngay.

## Câu trả lời luôn là từ chối

Triệu chứng: mọi câu hỏi đều nhận về câu từ chối, kể cả câu hỏi chắc chắn có đáp án
trong tài liệu. Nguyên nhân theo thứ tự khả năng giảm dần:

Bộ sưu tập rỗng vì chưa chạy kịch bản nạp, hoặc đã chạy nhưng vào một bộ sưu tập tên
khác. Kiểm tra số điểm trong bộ sưu tập trước tiên.

Ngưỡng điểm tương đồng đặt quá cao so với dữ liệu thật. Ngưỡng hợp lý phụ thuộc vào mô
hình sinh vector và vào độ tương đồng ngữ nghĩa giữa câu hỏi và tài liệu. Hạ ngưỡng
xuống rồi quan sát phân bố điểm thật trước khi chốt một giá trị.

Mô hình sinh vector đã đổi so với lúc nạp. Vector cũ và vector mới không cùng không
gian, nên mọi phép so khoảng cách đều vô nghĩa. Trường hợp này bắt buộc nạp lại toàn bộ.

## Kết quả trả về không liên quan

Triệu chứng: hệ thống trả lời trôi chảy nhưng trích dẫn sai đoạn văn. Đây là lỗi khó
nhất vì nó không tạo ra ngoại lệ nào.

Kiểm tra trước hết xem câu hỏi có chứa đại từ tham chiếu tới lượt hỏi trước không. Chỉ
câu hỏi hiện tại được đem đi sinh vector, nên một câu như giải thích rõ hơn đi sẽ không
mang đủ thông tin để tìm đúng đoạn.

Kiểm tra tiếp độ dài đoạn. Đoạn quá dài làm vector bị pha loãng, một đoạn nói về năm
chủ đề sẽ không gần với câu hỏi về bất kỳ chủ đề nào trong đó.

## Độ trễ tăng đột biến

Độ trễ của một truy vấn gồm ba phần: sinh vector cho câu hỏi, tìm kiếm trong kho vector,
và sinh câu trả lời. Phần sinh câu trả lời thường chiếm áp đảo, thường gấp vài chục lần
hai phần còn lại cộng lại.

Nếu đo thấy phần tìm kiếm chậm bất thường, nghi ngờ số điểm trong bộ sưu tập đã vượt
ngưỡng mà chỉ mục hiện tại phục vụ tốt. Nếu phần sinh vector chậm, nghi ngờ đường mạng
đi qua máy chủ trung gian.

## Nạp lại tài liệu không có tác dụng

Triệu chứng: sửa nội dung tệp, chạy lại kịch bản nạp, nhưng câu trả lời vẫn theo nội
dung cũ. Nguyên nhân thường là tên nguồn đã đổi, khiến bản cũ không bị xoá mà bản mới
được thêm vào song song. Liệt kê danh sách nguồn trong chỉ mục để đối chiếu.
