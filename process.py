from turtle import up
import cv2
from pylsd import lsd
import numpy as np
from scipy.spatial import distance as dist
from PIL import Image
from craft_text_detector import get_prediction
from pyimagesearch import imutils, transform

class Rule():
    def __init__(self, craft, refine, classifier):
        super().__init__()
        self.classifier = classifier
        self.craft = craft
        self.refine = refine
        self.color_dict = {'drug_name': (255, 0, 0), 'usage': (0, 255, 0), 'diagnose': (0, 0, 255), 'type': (255,255,0), 'quantity': (0,255,255), 'date': (255,0,255)}
    
    def detect(self, img):
        '''Detect text boxes'''
        text_boxes = get_prediction(
        image=img,
        craft_net=self.craft,
        refine_net=self.refine,
        text_threshold=0.7,
        link_threshold=0.4,
        # low_text=0.4,
        cuda=True,
        # long_size=1280
    )
        boxes = text_boxes['boxes']
        return boxes

    def rotate(self, img):
        '''Rotate the image'''
        height, width = img.shape[:2]

        crop_height = int(height/6)
        crop_width = int(width/6)

        crop = img[crop_height:height - crop_height, crop_width:width - crop_width]

        crop = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)

        crop = cv2.adaptiveThreshold(crop, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 15)

        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS,(50,9))
        crop = cv2.morphologyEx(crop, cv2.MORPH_OPEN, kernel)

        edged = cv2.Canny(crop, 0, 100)

        lines = lsd(edged)

        if lines is not None:
            lines = lines.squeeze().astype(np.int16).tolist()

            horizontal_lines_canvas = np.zeros(edged.shape, dtype=np.uint8)
            for line in lines:
                x1, y1, x2, y2, _ = line
                if abs(x2 - x1) > abs(y2 - y1):
                    (x1, y1), (x2, y2) = sorted(((x1, y1), (x2, y2)), key=lambda pt: pt[0])
                    cv2.line(horizontal_lines_canvas, (max(x1 - 5, 0), y1), (min(x2 + 5, img.shape[1] - 1), y2), 255, 2)

        (contours, _) = cv2.findContours(horizontal_lines_canvas, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

        contours = sorted(contours, key=lambda c: cv2.arcLength(c, True), reverse=True)[:1]

        #take longest contour
        contour = contours[0].reshape(contours[0].shape[0], contours[0].shape[2])

        min_x = np.amin(contour[:, 0], axis=0)
        max_x = np.amax(contour[:, 0], axis=0)
        left_y = int(np.average(contour[contour[:, 0] == min_x][:, 1]))
        right_y = int(np.average(contour[contour[:, 0] == max_x][:, 1]))

        sin = (left_y - right_y)/dist.euclidean((min_x, left_y), (max_x, right_y))
        angle = -np.arcsin(sin) * 180 / np.pi

        if abs(angle) > 25:
            return None

        rotated = imutils.rotate(img, angle)
        del contours
        del lines
        return rotated
    
    def check_line(self, img):
        '''Find height coordination of table's horizontal lines'''
        height, width = img.shape[:2]

        crop_width = int(width/6)
        crop = img[:, crop_width:width - crop_width, :]

        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)

        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 4)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS,(25,1))
        erode = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        edged = cv2.Canny(erode, 10, 20)

        lines = lsd(edged)

        if lines is not None:
            lines = lines.squeeze().astype(np.int16).tolist()
            # horizontal_lines_canvas = np.zeros(edged.shape, dtype=np.uint8)

            chosen = []
            for line in lines:
                x1, y1, x2, y2, _ = line
                
                if abs(x2 - x1) < width/20 or y1 < height//5 or y1 > height*4//5:
                    continue
                
                tan = abs(y1-y2)/abs(x1-x2)
                if tan > 0.03:
                    continue
                # cv2.line(horizontal_lines_canvas, (x1, y1), (x2, y2), 255, 2)
                chosen.append(line)
                
            lines  = sorted(chosen, key=lambda c: c[1], reverse=True)
            
        del chosen
        
        num = 0
        h_val = []
        start = lines[0]
        count = 0
        x_min = min(start[0], start[2])
        x_max = max(start[0], start[2])
        for i in range(1,len(lines)):
            x1, y1, x2, y2, _ = lines[i]
            if start[1] - y1 <= width/60:
                count += 1
                x_min = min(x_min, x1, x2)
                x_max = max(x_max, x1, x2)
            else:
                if x_max - x_min > width//4:
                    num += 1
                    h_val.append(start[1])
                count = 0
                start = lines[i]
                x_min = min(start[0], start[2])
                x_max = max(start[0], start[2])
        if x_max - x_min > width//4:
            num += 1
            h_val.append(start[1])
        del lines
        # for val in h_val:
        #     cv2.line(horizontal_lines_canvas, (0, val), (500, val), 255, 2)
        # print(h_val)
        # cv2.imwrite('line.jpg', horizontal_lines_canvas)
        return h_val

    def predict(self, img):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        im_pil = Image.fromarray(img)
        s = self.classifier.predict(im_pil)
        return s

    def draw_box(self, img, pts, color, cut):
        if color[0] == 122:
            thickness = 15
        else: thickness = 3
        # print(pts)
        pts = pts.astype(int)
        pts[:, 1] += cut
        for i in range(4):
            cv2.line(img, tuple(pts[i-1]), tuple(pts[i]), color, thickness=thickness)
        return

    def row(self, img, pts, label):
        x_min = min(pts[:, 0])
        x_max = max(pts[:, 0])
        y_min = min(pts[:, 1])
        y_max = max(pts[:, 1])
        warp = transform.four_point_transform(img, pts)
        ocr = self.predict(warp)
        return [int(x_min), int(y_min), int(x_max), int(y_max), ocr, label]

    def case1(self, img, csv_writer):
        img = self.rotate(img)
        origin = img
        cut = 0
        height, width = img.shape[:2]
        h_val = self.check_line(img)
        # for val in h_val:
        #     cv2.line(img, (0, val), (500, val), (255, 255, 0), 2)

        if len(h_val) < 2:
            return img
        if h_val[-2] - h_val[-1] > height // 20:
            h_val.remove(h_val[-1])
        h_min = h_val[-2]- width//50
        h_max = h_val[0] - width//100
        # for val in h_val:
        #     cv2.line
        upper = []
        inside_table = []
        # dt_boxes, _ = self.detector(img)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        dt_boxes = self.detect(img)
        no = 0
        lst_boxes = []
        for box in dt_boxes:
            lst_boxes.append([box, no])
            # print(lst_boxes)
            no += 1
        del dt_boxes
        lst_boxes = sorted(lst_boxes, key=lambda c: c[0][0][1], reverse=True)
        
        # print(height/dt_boxes[-1][0][1])
        first = -1
        while True:
            x1, y1 = lst_boxes[first][0][0]
            x2, y2 = lst_boxes[first][0][1]
            tan = abs(y1-y2)/abs(x1-x2)
            if tan < 0.03 and x2 - x1 > width//15:
                break
            first -= 1
        # self.draw_box(img, lst_boxes[0][first], (122,122,0))
        if lst_boxes[first][0][0][1] > height//9:
            cut = int(lst_boxes[first][0][0][1]) - height//20
            img = img[cut:, :,:]
            h_val = self.check_line(img)
            if len(h_val) < 2:
                return origin
            h_min = h_val[-2]- width//50
            h_max = h_val[0] - width//100
            for box in lst_boxes:
                box[0][:,1] -= cut
            height -= cut
        back = 3
        date_done = 0
        result = []

        for i in range(len(lst_boxes)):
            pts = lst_boxes[i][0]
            pts = pts.astype(np.int16)
            dist = np.linalg.norm(pts[0] - pts[2])

            if dist < width//13 and pts[0][0] < width//70:
                if pts[0][1] - h_max < height//15:
                    # self.draw_box(img, pts, (122,122))
                    # print(pts, 'a')
                    result.append([self.row(img, pts, 'other'), lst_boxes[i][1]])
                    back += 1
                continue
            
            if dist < width//20 and pts[0][1] < h_max + height//25 and pts[0][1] > h_max:
                # self.draw_box(img, pts, (122,122,122))
                # print(pts, 'b')
                back += 1
                result.append([self.row(img, pts, 'other'), lst_boxes[i][1]])
                continue
            
            if dist > width//35 and pts[0,1] > h_min and pts[0,1] < h_max:
                if date_done == 0:
                    # for j in range (back):
                    # print(back)
                    date_box = [lst_boxes[i-back][0].astype(np.int16), lst_boxes[i][1]]
                    date_done = 1
                inside_table.append([pts, lst_boxes[i][1]])
            elif pts[0,1] < h_val[-1] - height//80:
                upper.append([pts,lst_boxes[i][1]])
            else:
                result.append([self.row(img, pts, 'other'), lst_boxes[i][1]])
        del lst_boxes
        if date_done == 1:
            self.draw_box(origin, date_box[0], self.color_dict['date'], cut)
            result.append([self.row(img, date_box[0], 'date'), date_box[1]])
        # for pts in upper:
        #     self.draw_box(img, pts, (122, 122, 0))

        phong_kham = upper[0][0]
        result.append([self.row(img, upper[0][0], 'other'), upper[0][1]])
        if abs(upper[1][0][0][1] - phong_kham[0][1]) < height // 120:
            begin = 2
            x_val = min(phong_kham[0][0], upper[1][0][0][0])
            result.append([self.row(img, upper[1][0], 'other'), upper[1][1]])
        else:
            begin = 1
            x_val = phong_kham[0][0]

        for i in range (begin, len(upper)):
            if x_val - upper[i][0][0][0] > width // 60:
                result.append([self.row(img, upper[i][0], 'other'), upper[i][1]])
                continue
            result.append([self.row(img, upper[i][0], 'diagnose'), upper[i][1]])
            self.draw_box(origin, upper[i][0], self.color_dict['diagnose'], cut)
            if upper[i][0][0][0] - x_val < width//50:
                for j in range(i+1, len(upper)):
                    result.append([self.row(img, upper[j][0], 'other'), upper[j][1]])
                break
        
        del upper

        name_usage = []
        type = []
        quantity = []
        type_start = 0
        max_width = 0
        

        inside_table = sorted(inside_table, key=lambda c: c[0][0][0])
        # print(inside_table)
        for i in range(1, len(inside_table)):
            if inside_table[i][0][2][0] - inside_table[i][0][0][0] > inside_table[max_width][0][2][0] - inside_table[max_width][0][0][0]:
                max_width = i


        for item in inside_table:
            pts = item[0]
            if inside_table[max_width][0][0][0] - pts[0][0] > width//30:
                result.append([self.row(img, pts, 'other'), item[1]])
                continue
            if abs(inside_table[max_width][0][0][0] - pts[0][0]) < width//20:
                name_usage.append(item)
            elif type_start == 0:
                type_start = pts[0][0]
                # type.append(pts)
                result.append([self.row(img, pts, 'type'), item[1]])
                self.draw_box(origin, pts, self.color_dict['type'], cut)
            elif pts[0][0] - type_start < width // 30:
                # type.append(pts)
                result.append([self.row(img, pts, 'type'), item[1]])
                self.draw_box(origin, pts, self.color_dict['type'], cut)
            else:
                # quantity.append(pts)
                result.append([self.row(img, pts, 'quantity'), item[1]])
                self.draw_box(origin, pts, self.color_dict['quantity'], cut)

        del inside_table
        
        # type = sorted(type, key=lambda c: c[0][1], reverse=True)
        # quantity = sorted(quantity, key=lambda c: c[0][1])

        line_idx = 1
        count = 0

        # print(name_usage)
        name_usage = sorted(name_usage, key=lambda c: c[0][0][1], reverse=True)
        # quantity = sorted(quantity, key=lambda c: c[0][1], reverse=True)
        # type = sorted(type, key=lambda c: c[0][1], reverse=True)

        # quan_idx = 0
        # type_idx = 0

        for i in range(len(name_usage)):
            if i == len(name_usage) - 1 or name_usage[i+1][0][0][1] < h_val[line_idx] - height//100:
                self.draw_box(origin, name_usage[i][0], self.color_dict['drug_name'], cut)
                result.append([self.row(img, name_usage[i][0], 'drug_name'), name_usage[i][1]])
                count = 0
                line_idx += 1
            else:
                if count == 0:
                    result.append([self.row(img, name_usage[i][0], 'usage'), name_usage[i][1]])
                    count = 1
                    self.draw_box(origin, name_usage[i][0], self.color_dict['usage'], cut)
                    # if quan_idx < len(quantity) and quantity[quan_idx][0][1] > h_val[line_idx] - height//100:
                    #     result.append(self.row(img, quantity[quan_idx], 'quantity'), pts[4])
                    #     quan_idx += 1
                    # if type_idx < len(type) and type[type_idx][0][1] > h_val[line_idx] - height//70:
                    #     result.append(self.row(img, type[type_idx], 'type'), pts[4])
                    #     type_idx += 1
                else:
                    self.draw_box(origin, name_usage[i][0], self.color_dict['drug_name'], cut)
                    result.append([self.row(img, name_usage[i][0], 'drug_name'), name_usage[i][1]])
        if cut != 0:
            for item in result:
                item[0][1] += cut
                item[0][3] += cut
        result = sorted(result, key=lambda c: c[1])
        for item in result:
            csv_writer.writerow(item[0])
        del name_usage
        del type
        del quantity
        del h_val
        
        return origin

